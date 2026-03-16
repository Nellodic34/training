#!/usr/bin/env python3

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Point, PoseStamped, Vector3Stamped
from nav_msgs.msg import Odometry, Path
from visualization_msgs.msg import Marker, MarkerArray
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image
from tf2_ros import Buffer, TransformListener
from ultralytics import YOLO


def quat_to_rotmat(x: float, y: float, z: float, w: float) -> np.ndarray:
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z

    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def stamp_to_ns(stamp) -> int:
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 1e-9:
        raise ValueError('Cannot normalize near-zero vector')
    return vec / norm


def triangulate_midpoint(
    origin_a: np.ndarray,
    dir_a: np.ndarray,
    origin_b: np.ndarray,
    dir_b: np.ndarray,
) -> Tuple[np.ndarray, float]:
    w0 = origin_a - origin_b
    a = float(np.dot(dir_a, dir_a))
    b = float(np.dot(dir_a, dir_b))
    c = float(np.dot(dir_b, dir_b))
    d = float(np.dot(dir_a, w0))
    e = float(np.dot(dir_b, w0))
    denom = a * c - b * b

    if abs(denom) < 1e-9:
        midpoint = 0.5 * (origin_a + origin_b)
        return midpoint, float(np.linalg.norm(origin_a - origin_b))

    s = (b * e - c * d) / denom
    t = (a * e - b * d) / denom

    closest_a = origin_a + s * dir_a
    closest_b = origin_b + t * dir_b
    midpoint = 0.5 * (closest_a + closest_b)
    error = float(np.linalg.norm(closest_a - closest_b))
    return midpoint, error


@dataclass
class StateCov:
    """State and covariance pair (equivalent to mrs_lib::LKF::statecov_t)."""

    x: np.ndarray  # state vector  (n,)
    P: np.ndarray  # covariance     (n, n)


class LinearKalmanFilter:


    def __init__(self, A: np.ndarray, B: np.ndarray, H: np.ndarray) -> None:
        self.A = A.copy()
        self.B = B.copy()
        self.H = H.copy()
        self.n = A.shape[0]

    def predict(self, sc: StateCov, u: np.ndarray, Q: np.ndarray, dt: float) -> StateCov:
        """Prediction step.  Q is scaled by dt (same as mrs_lib::LKF::predict)."""
        x_pred = self.A @ sc.x + self.B @ u
        P_pred = self.A @ sc.P @ self.A.T + Q * dt
        return StateCov(x=x_pred, P=P_pred)

    def correct(self, sc: StateCov, z: np.ndarray, R: np.ndarray) -> StateCov:
        """Correction (update) step."""
        y = z - self.H @ sc.x
        S = self.H @ sc.P @ self.H.T + R
        K = sc.P @ self.H.T @ np.linalg.inv(S)
        x_new = sc.x + K @ y
        P_new = (np.eye(self.n) - K @ self.H) @ sc.P
        return StateCov(x=x_new, P=P_new)


def build_transition_matrix(dt: float) -> np.ndarray:
    """Build 9x9 constant-acceleration (CA) transition matrix A(dt).

    State layout: [px, py, pz, vx, vy, vz, ax, ay, az]
    """
    A = np.eye(9, dtype=np.float64)
    dt2 = 0.5 * dt * dt
    # position += v*dt + 0.5*a*dt^2
    A[0, 3] = dt;  A[0, 6] = dt2
    A[1, 4] = dt;  A[1, 7] = dt2
    A[2, 5] = dt;  A[2, 8] = dt2
    # velocity += a*dt
    A[3, 6] = dt
    A[4, 7] = dt
    A[5, 8] = dt
    return A


@dataclass
class DetectionObservation:
    stamp_ns: int
    center_u: float
    center_v: float
    confidence: float
    class_id: int
    class_name: str


class TestYolov8MultiViewTriangulationNode(Node):
    def __init__(self) -> None:
        super().__init__('test_yolov8_multiview_triangulation_node')

        self.declare_parameter('observer1_name', 'uav1')
        self.declare_parameter('observer2_name', 'uav2')
        self.declare_parameter('target_name', 'uav3')
        self.declare_parameter('pose_topic', '/target/pose_estimate')
        self.declare_parameter('odometry_topic', '/target/odometry_estimate')
        self.declare_parameter('estimated_position_topic', '/target/position_estimate')
        self.declare_parameter('error_vector_topic', '/target/position_error')
        self.declare_parameter('target_frame_id', 'world')
        self.declare_parameter(
            'model_path',
            '~/datasets/uav_detector/20260227_174226/runs/detect/exp1/run1_debug2/weights/best.pt',
        )
        self.declare_parameter('confidence_threshold', 0.25)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('imgsz', 640)
        self.declare_parameter('max_detections', 100)
        self.declare_parameter('device', 'cpu')
        self.declare_parameter('line_width', 2)
        self.declare_parameter('target_class_id', -1)
        self.declare_parameter('max_pair_age_sec', 0.75)
        self.declare_parameter('triangulation_min_baseline_m', 0.25)
        self.declare_parameter('max_triangulation_error_m', 2.0)
        self.declare_parameter('max_target_gt_age_sec', 0.75)
        self.declare_parameter('processing_rate_hz', 5.0)
        self.declare_parameter('tf_timeout_sec', 0.1)
        self.declare_parameter('world_frame_suffix', 'world_origin')
        self.declare_parameter('kf_process_noise_pos', 0.5)   # Q_pos
        self.declare_parameter('kf_process_noise_vel', 1.0)   # Q_vel
        self.declare_parameter('kf_process_noise_acc', 2.0)   # Q_acc (higher = faster adaptation to manoeuvres)
        self.declare_parameter('kf_measurement_noise', 0.05)  # R
        self.declare_parameter('kf_initial_covariance', 10.0)
        self.declare_parameter('kf_prediction_horizon_sec', 2.0)  # seconds ahead to predict
        self.declare_parameter('kf_prediction_steps', 25)          # path samples over the horizon

        self.observer1_name = str(self.get_parameter('observer1_name').value)
        self.observer2_name = str(self.get_parameter('observer2_name').value)
        self.target_name = str(self.get_parameter('target_name').value)

        self.observer_roles = ['observer1', 'observer2']
        self.observer_uav_names = {
            'observer1': self.observer1_name,
            'observer2': self.observer2_name,
        }

        self.image_topics: Dict[str, str] = {}
        self.detection_topics: Dict[str, str] = {}
        self.camera_info_topics: Dict[str, str] = {}
        for role, uav in self.observer_uav_names.items():
            self.image_topics[role] = f'/{uav}/rgb/image_raw'
            self.detection_topics[role] = f'/{uav}/detection'
            self.camera_info_topics[role] = f'/{uav}/rgb/camera_info'
        self.target_gt_odom_topic = f'/{self.target_name}/hw_api/ground_truth'

        self.pose_topic = str(self.get_parameter('pose_topic').value)
        self.odometry_topic = str(self.get_parameter('odometry_topic').value)
        self.estimated_position_topic = str(self.get_parameter('estimated_position_topic').value)
        self.error_vector_topic = str(self.get_parameter('error_vector_topic').value)
        self.target_frame_id = str(self.get_parameter('target_frame_id').value)
        self.model_path = os.path.expanduser(str(self.get_parameter('model_path').value))
        self.confidence_threshold = float(self.get_parameter('confidence_threshold').value)
        self.iou_threshold = float(self.get_parameter('iou_threshold').value)
        self.imgsz = int(self.get_parameter('imgsz').value)
        self.max_detections = int(self.get_parameter('max_detections').value)
        self.device = str(self.get_parameter('device').value)
        self.line_width = max(1, int(self.get_parameter('line_width').value))
        self.target_class_id = int(self.get_parameter('target_class_id').value)
        self.max_pair_age_ns = int(float(self.get_parameter('max_pair_age_sec').value) * 1_000_000_000.0)
        self.triangulation_min_baseline_m = float(self.get_parameter('triangulation_min_baseline_m').value)
        self.max_triangulation_error_m = float(self.get_parameter('max_triangulation_error_m').value)
        self.max_target_gt_age_ns = int(float(self.get_parameter('max_target_gt_age_sec').value) * 1_000_000_000.0)
        self.processing_rate_hz = max(0.5, float(self.get_parameter('processing_rate_hz').value))
        self.tf_timeout_sec = float(self.get_parameter('tf_timeout_sec').value)
        self.world_frame_suffix = str(self.get_parameter('world_frame_suffix').value)
        self.kf_process_noise_pos = float(self.get_parameter('kf_process_noise_pos').value)
        self.kf_process_noise_vel = float(self.get_parameter('kf_process_noise_vel').value)
        self.kf_process_noise_acc = float(self.get_parameter('kf_process_noise_acc').value)
        self.kf_measurement_noise = float(self.get_parameter('kf_measurement_noise').value)
        self.kf_initial_covariance = float(self.get_parameter('kf_initial_covariance').value)
        self.kf_prediction_horizon_sec = float(self.get_parameter('kf_prediction_horizon_sec').value)
        self.kf_prediction_steps = max(5, int(self.get_parameter('kf_prediction_steps').value))

        # If target_frame_id was left as the generic default 'world', auto-derive it from observer1 +
        # world_frame_suffix so that published poses are in the same TF frame used by triangulation.
        if self.target_frame_id == 'world':
            self.target_frame_id = f'{self.observer1_name}/{self.world_frame_suffix}'
        self.get_logger().info(f'Publishing all estimate topics in frame: {self.target_frame_id}')

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f'Model not found: {self.model_path}')

        self.bridge = CvBridge()
        self.model = YOLO(self.model_path)
        self.model.fuse()

        self.camera_infos: Dict[str, Optional[CameraInfo]] = {r: None for r in self.observer_roles}
        self.observations: Dict[str, Optional[DetectionObservation]] = {r: None for r in self.observer_roles}
        self.latest_images: Dict[str, Optional[Image]] = {r: None for r in self.observer_roles}
        self.last_processed_image_stamp_ns: Dict[str, int] = {r: -1 for r in self.observer_roles}
        self.target_gt_odom: Optional[Odometry] = None

        # --- Linear Kalman Filter (constant-acceleration model, CA) ---
        # State: [px, py, pz, vx, vy, vz, ax, ay, az],  Measurement: [px, py, pz]
        A0 = np.eye(9, dtype=np.float64)        # updated with dt before each predict
        B0 = np.zeros((9, 1), dtype=np.float64)  # no control input
        H0 = np.zeros((3, 9), dtype=np.float64)
        H0[0, 0] = H0[1, 1] = H0[2, 2] = 1.0
        self.kf = LinearKalmanFilter(A0, B0, H0)
        self.kf_Q = np.diag([
            self.kf_process_noise_pos, self.kf_process_noise_pos, self.kf_process_noise_pos,
            self.kf_process_noise_vel, self.kf_process_noise_vel, self.kf_process_noise_vel,
            self.kf_process_noise_acc, self.kf_process_noise_acc, self.kf_process_noise_acc,
        ])
        self.kf_R = np.eye(3, dtype=np.float64) * self.kf_measurement_noise
        self.kf_u = np.zeros(1, dtype=np.float64)
        self.kf_sc: Optional[StateCov] = None
        self.kf_last_stamp_ns: Optional[int] = None

        self.last_error_log_time = time.time()
        self.frame_counter = 0
        self.last_log_time = time.time()

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        self.detection_pubs = {}
        for role in self.observer_roles:
            self.detection_pubs[role] = self.create_publisher(Image, self.detection_topics[role], 10)
        self.pose_pub = self.create_publisher(PoseStamped, self.pose_topic, 10)
        self.odometry_pub = self.create_publisher(Odometry, self.odometry_topic, 10)
        self.estimated_position_pub = self.create_publisher(Vector3Stamped, self.estimated_position_topic, 10)
        self.error_vector_pub = self.create_publisher(Vector3Stamped, self.error_vector_topic, 10)
        self.predicted_trajectory_pub = self.create_publisher(Path, '/target/predicted_trajectory', 10)
        self.trajectory_markers_pub = self.create_publisher(MarkerArray, '/target/predicted_trajectory_markers', 10)
        self.position_markers_pub = self.create_publisher(MarkerArray, '/target/position_markers', 10)

        for role in self.observer_roles:
            self.create_subscription(
                Image, self.image_topics[role],
                lambda msg, r=role: self.image_callback(r, msg), 1,
            )
            self.create_subscription(
                CameraInfo, self.camera_info_topics[role],
                lambda msg, r=role: self.camera_info_callback(r, msg), 10,
            )
        self.create_subscription(Odometry, self.target_gt_odom_topic, self.target_gt_odom_callback, 20)
        self.create_timer(1.0 / self.processing_rate_hz, self.processing_timer_callback)

        self.get_logger().info(f'YOLO model path: {self.model_path}')
        for role in self.observer_roles:
            uav = self.observer_uav_names[role]
            self.get_logger().info(
                f'{role} ({uav}): {self.image_topics[role]} -> {self.detection_topics[role]}'
            )
        self.get_logger().info(f'Target UAV: {self.target_name} (GT: {self.target_gt_odom_topic})')
        self.get_logger().info(f'TF world frame suffix: {self.world_frame_suffix}')
        self.get_logger().info(f'Pose topic: {self.pose_topic}')
        self.get_logger().info(f'Odometry topic: {self.odometry_topic}')
        self.get_logger().info(f'Estimated position topic: {self.estimated_position_topic}')
        self.get_logger().info(f'Error vector topic: {self.error_vector_topic}')
        self.get_logger().info(f'Processing rate: {self.processing_rate_hz:.1f} Hz')

    def camera_info_callback(self, role: str, msg: CameraInfo) -> None:
        self.camera_infos[role] = msg

    def target_gt_odom_callback(self, msg: Odometry) -> None:
        self.target_gt_odom = msg

    def image_callback(self, role: str, msg: Image) -> None:
        self.latest_images[role] = msg

    def processing_timer_callback(self) -> None:
        for role in self.observer_roles:
            self.process_latest_image(role, self.detection_pubs[role])

    def process_latest_image(self, uav_name: str, publisher) -> None:
        msg = self.latest_images[uav_name]
        if msg is None:
            return

        stamp_ns = stamp_to_ns(msg.header.stamp)
        if stamp_ns <= self.last_processed_image_stamp_ns[uav_name]:
            return

        self.last_processed_image_stamp_ns[uav_name] = stamp_ns
        self.process_image(uav_name, msg, publisher)

    def process_image(self, uav_name: str, msg: Image, publisher) -> None:
        try:
            bgr_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().error(f'[{uav_name}] Failed to convert input image: {exc}')
            return

        start_time = time.time()
        results = self.model.predict(
            source=bgr_image,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            imgsz=self.imgsz,
            max_det=self.max_detections,
            device=self.device,
            verbose=False,
        )
        infer_ms = (time.time() - start_time) * 1000.0

        best_detection = self.extract_best_detection(results, msg)
        annotated_image = self.draw_predictions(bgr_image, results, best_detection)
        out_msg = self.bridge.cv2_to_imgmsg(annotated_image, encoding='bgr8')
        out_msg.header = msg.header
        publisher.publish(out_msg)

        self.observations[uav_name] = best_detection
        self.try_triangulate()

        self.frame_counter += 1
        now = time.time()
        if now - self.last_log_time >= 2.0:
            fps = self.frame_counter / (now - self.last_log_time)
            self.get_logger().info(f'Multi-view test: FPS={fps:.2f}, last_inference={infer_ms:.1f}ms')
            self.frame_counter = 0
            self.last_log_time = now

    def extract_best_detection(self, results, msg: Image) -> Optional[DetectionObservation]:
        if not results:
            return None

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            return None

        names = result.names if result.names is not None else {}
        boxes_xyxy: List[Tuple[float, float, float, float]] = result.boxes.xyxy.tolist()
        confidences: List[float] = result.boxes.conf.tolist()
        classes: List[float] = result.boxes.cls.tolist()

        candidates: List[DetectionObservation] = []
        for box, conf, cls_idx in zip(boxes_xyxy, confidences, classes):
            class_id = int(cls_idx)
            if self.target_class_id >= 0 and class_id != self.target_class_id:
                continue

            x1, y1, x2, y2 = box
            center_u = 0.5 * (x1 + x2)
            center_v = 0.5 * (y1 + y2)
            class_name = names.get(class_id, str(class_id)) if isinstance(names, dict) else str(class_id)
            candidates.append(
                DetectionObservation(
                    stamp_ns=stamp_to_ns(msg.header.stamp),
                    center_u=center_u,
                    center_v=center_v,
                    confidence=float(conf),
                    class_id=class_id,
                    class_name=class_name,
                )
            )

        if not candidates:
            return None

        return max(candidates, key=lambda item: item.confidence)

    def draw_predictions(self, image: np.ndarray, results, best_detection: Optional[DetectionObservation]) -> np.ndarray:
        annotated = image.copy()

        if not results:
            return annotated

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            return annotated

        names = result.names if result.names is not None else {}
        boxes_xyxy: List[Tuple[float, float, float, float]] = result.boxes.xyxy.tolist()
        confidences: List[float] = result.boxes.conf.tolist()
        classes: List[float] = result.boxes.cls.tolist()

        for box, conf, cls_idx in zip(boxes_xyxy, confidences, classes):
            x1, y1, x2, y2 = [int(v) for v in box]
            class_id = int(cls_idx)
            class_name = names.get(class_id, str(class_id)) if isinstance(names, dict) else str(class_id)
            label = f'{class_name} {conf:.2f}'

            color = (0, 255, 0)
            if best_detection is not None:
                center_u = 0.5 * (box[0] + box[2])
                center_v = 0.5 * (box[1] + box[3])
                if abs(center_u - best_detection.center_u) < 1.0 and abs(center_v - best_detection.center_v) < 1.0:
                    color = (0, 165, 255)
                    label += ' *'

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, self.line_width)
            y_text = y1 - 10 if y1 > 20 else y1 + 20
            cv2.putText(
                annotated,
                label,
                (x1, y_text),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

        return annotated

    def try_triangulate(self) -> None:
        obs1 = self.observations['observer1']
        obs2 = self.observations['observer2']
        info1 = self.camera_infos['observer1']
        info2 = self.camera_infos['observer2']

        if obs1 is None or obs2 is None or info1 is None or info2 is None:
            return

        if abs(obs1.stamp_ns - obs2.stamp_ns) > self.max_pair_age_ns:
            return

        result1 = self.pixel_to_world_ray(info1, obs1.stamp_ns, obs1.center_u, obs1.center_v)
        result2 = self.pixel_to_world_ray(info2, obs2.stamp_ns, obs2.center_u, obs2.center_v)

        if result1 is None or result2 is None:
            return

        origin1, dir1 = result1
        origin2, dir2 = result2

        baseline = float(np.linalg.norm(origin2 - origin1))
        if baseline < self.triangulation_min_baseline_m:
            return

        midpoint, error = triangulate_midpoint(origin1, dir1, origin2, dir2)
        if error > self.max_triangulation_error_m:
            self.get_logger().warn(
                f'Triangulation rejected: ray mismatch {error:.2f} m exceeds {self.max_triangulation_error_m:.2f} m'
            )
            return

        stamp_ns = max(obs1.stamp_ns, obs2.stamp_ns)
        measurement = midpoint

        # --- KF predict + correct ---
        if self.kf_sc is None:
            x0 = np.zeros(9, dtype=np.float64)
            x0[:3] = measurement
            P0 = np.eye(9, dtype=np.float64) * self.kf_initial_covariance
            self.kf_sc = StateCov(x=x0, P=P0)
            self.kf_last_stamp_ns = stamp_ns
        else:
            dt = (stamp_ns - self.kf_last_stamp_ns) / 1_000_000_000.0
            if dt > 0.0:
                self.kf.A = build_transition_matrix(dt)
                self.kf_sc = self.kf.predict(self.kf_sc, self.kf_u, self.kf_Q, dt)
                self.kf_last_stamp_ns = stamp_ns
        self.kf_sc = self.kf.correct(self.kf_sc, measurement, self.kf_R)

        filtered_position     = self.kf_sc.x[:3].copy()
        filtered_velocity     = self.kf_sc.x[3:6].copy()
        filtered_acceleration = self.kf_sc.x[6:9].copy()

        self.publish_pose_estimate(filtered_position, filtered_velocity, filtered_acceleration, stamp_ns)
        self.publish_ground_truth_error(filtered_position, stamp_ns)

    def pixel_to_world_ray(
        self,
        camera_info: CameraInfo,
        stamp_ns: int,
        u: float,
        v: float,
    ) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        fx = float(camera_info.k[0])
        fy = float(camera_info.k[4])
        cx = float(camera_info.k[2])
        cy = float(camera_info.k[5])

        ray_optical = normalize(np.array([(u - cx) / fx, (v - cy) / fy, 1.0], dtype=np.float64))

        camera_frame = camera_info.header.frame_id
        prefix = camera_frame.split('/')[0] if '/' in camera_frame else camera_frame
        world_frame = f'{prefix}/{self.world_frame_suffix}'

        try:
            sec = stamp_ns // 1_000_000_000
            nanosec = stamp_ns % 1_000_000_000
            lookup_time = Time(seconds=sec, nanoseconds=nanosec)
            timeout = Duration(seconds=self.tf_timeout_sec)
            transform = self.tf_buffer.lookup_transform(
                world_frame, camera_frame, lookup_time, timeout
            )
        except Exception as exc:
            self.get_logger().warn(
                f'TF lookup {world_frame} <- {camera_frame} failed: {exc}',
                throttle_duration_sec=2.0,
            )
            return None

        t = transform.transform.translation
        q = transform.transform.rotation
        camera_origin_world = np.array([t.x, t.y, t.z], dtype=np.float64)
        r_wc = quat_to_rotmat(q.x, q.y, q.z, q.w)
        ray_world = normalize(r_wc @ ray_optical)
        return camera_origin_world, ray_world

    def publish_pose_estimate(self, position: np.ndarray, velocity: np.ndarray, acceleration: np.ndarray, stamp_ns: int) -> None:
        sec = stamp_ns // 1_000_000_000
        nanosec = stamp_ns % 1_000_000_000

        estimated_position_msg = Vector3Stamped()
        estimated_position_msg.header.frame_id = self.target_frame_id
        estimated_position_msg.header.stamp.sec = int(sec)
        estimated_position_msg.header.stamp.nanosec = int(nanosec)
        estimated_position_msg.vector.x = float(position[0])
        estimated_position_msg.vector.y = float(position[1])
        estimated_position_msg.vector.z = float(position[2])
        self.estimated_position_pub.publish(estimated_position_msg)

        pose_msg = PoseStamped()
        pose_msg.header.frame_id = self.target_frame_id
        pose_msg.header.stamp.sec = int(sec)
        pose_msg.header.stamp.nanosec = int(nanosec)
        pose_msg.pose.position.x = float(position[0])
        pose_msg.pose.position.y = float(position[1])
        pose_msg.pose.position.z = float(position[2])
        pose_msg.pose.orientation.w = 1.0
        self.pose_pub.publish(pose_msg)

        # Covariance from KF state (if available)
        P = self.kf_sc.P if self.kf_sc is not None else np.eye(9)

        odom_msg = Odometry()
        odom_msg.header = pose_msg.header
        odom_msg.child_frame_id = 'target_estimate'
        odom_msg.pose.pose = pose_msg.pose
        odom_msg.pose.covariance[0] = float(P[0, 0])
        odom_msg.pose.covariance[7] = float(P[1, 1])
        odom_msg.pose.covariance[14] = float(P[2, 2])

        odom_msg.twist.twist.linear.x = float(velocity[0])
        odom_msg.twist.twist.linear.y = float(velocity[1])
        odom_msg.twist.twist.linear.z = float(velocity[2])
        odom_msg.twist.covariance[0] = float(P[3, 3])
        odom_msg.twist.covariance[7] = float(P[4, 4])
        odom_msg.twist.covariance[14] = float(P[5, 5])

        self.odometry_pub.publish(odom_msg)
        self._publish_predicted_trajectory(position, velocity, acceleration, stamp_ns)
        self._publish_position_markers(position, stamp_ns)

    def _publish_predicted_trajectory(
        self,
        position: np.ndarray,
        velocity: np.ndarray,
        acceleration: np.ndarray,
        stamp_ns: int,
    ) -> None:
        """Publish predicted CA trajectory as a Path and as RViz arrow markers."""
        sec = int(stamp_ns // 1_000_000_000)
        nanosec = int(stamp_ns % 1_000_000_000)

        path_msg = Path()
        path_msg.header.frame_id = self.target_frame_id
        path_msg.header.stamp.sec = sec
        path_msg.header.stamp.nanosec = nanosec

        dt_step = self.kf_prediction_horizon_sec / self.kf_prediction_steps
        pred_points: List[np.ndarray] = []
        for i in range(self.kf_prediction_steps + 1):
            t = i * dt_step
            pred_pos = position + velocity * t + 0.5 * acceleration * (t * t)
            pred_points.append(pred_pos)

            pred_stamp_ns = stamp_ns + int(t * 1_000_000_000)
            pose = PoseStamped()
            pose.header.frame_id = self.target_frame_id
            pose.header.stamp.sec = int(pred_stamp_ns // 1_000_000_000)
            pose.header.stamp.nanosec = int(pred_stamp_ns % 1_000_000_000)
            pose.pose.position.x = float(pred_pos[0])
            pose.pose.position.y = float(pred_pos[1])
            pose.pose.position.z = float(pred_pos[2])
            pose.pose.orientation.w = 1.0
            path_msg.poses.append(pose)

        self.predicted_trajectory_pub.publish(path_msg)

        # --- Arrow markers (yellow → red gradient along the horizon) ---
        marker_array = MarkerArray()

        # DELETEALL clears leftover arrows from previous frames
        clear = Marker()
        clear.header.frame_id = self.target_frame_id
        clear.header.stamp.sec = sec
        clear.header.stamp.nanosec = nanosec
        clear.ns = 'predicted_traj'
        clear.action = Marker.DELETEALL
        marker_array.markers.append(clear)

        n_segments = len(pred_points) - 1
        for i in range(n_segments):
            alpha = i / max(1, n_segments - 1)  # 0 (near/yellow) → 1 (far/red)
            m = Marker()
            m.header.frame_id = self.target_frame_id
            m.header.stamp.sec = sec
            m.header.stamp.nanosec = nanosec
            m.ns = 'predicted_traj'
            m.id = i + 1
            m.type = Marker.ARROW
            m.action = Marker.ADD
            m.scale.x = 0.06   # shaft diameter [m]
            m.scale.y = 0.14   # head diameter  [m]
            m.scale.z = 0.0    # head length 0 → auto
            m.color.r = 1.0
            m.color.g = float(1.0 - alpha)
            m.color.b = 0.0
            m.color.a = float(0.9 - 0.45 * alpha)
            m.lifetime.sec = 1  # auto-expire so stale arrows vanish
            p0 = pred_points[i]
            p1 = pred_points[i + 1]
            m.points = [
                Point(x=float(p0[0]), y=float(p0[1]), z=float(p0[2])),
                Point(x=float(p1[0]), y=float(p1[1]), z=float(p1[2])),
            ]
            marker_array.markers.append(m)

        self.trajectory_markers_pub.publish(marker_array)

    def _publish_position_markers(self, position: np.ndarray, stamp_ns: int) -> None:
        """Publish a blue sphere (estimated) and a green sphere (GT) in RViz."""
        sec = int(stamp_ns // 1_000_000_000)
        nanosec = int(stamp_ns % 1_000_000_000)
        marker_array = MarkerArray()

        # Blue sphere – estimated position
        est = Marker()
        est.header.frame_id = self.target_frame_id
        est.header.stamp.sec = sec
        est.header.stamp.nanosec = nanosec
        est.ns = 'position_estimate'
        est.id = 0
        est.type = Marker.SPHERE
        est.action = Marker.ADD
        est.pose.position.x = float(position[0])
        est.pose.position.y = float(position[1])
        est.pose.position.z = float(position[2])
        est.pose.orientation.w = 1.0
        est.scale.x = est.scale.y = est.scale.z = 0.4
        est.color.r = 0.0
        est.color.g = 0.4
        est.color.b = 1.0
        est.color.a = 0.9
        est.lifetime.sec = 1
        marker_array.markers.append(est)

        # Green sphere – ground-truth position (only when fresh)
        if self.target_gt_odom is not None:
            gt_stamp_ns = stamp_to_ns(self.target_gt_odom.header.stamp)
            if abs(stamp_ns - gt_stamp_ns) <= self.max_target_gt_age_ns:
                gt = Marker()
                gt.header.frame_id = self.target_frame_id
                gt.header.stamp.sec = sec
                gt.header.stamp.nanosec = nanosec
                gt.ns = 'position_ground_truth'
                gt.id = 1
                gt.type = Marker.SPHERE
                gt.action = Marker.ADD
                gt.pose.position.x = float(self.target_gt_odom.pose.pose.position.x)
                gt.pose.position.y = float(self.target_gt_odom.pose.pose.position.y)
                gt.pose.position.z = float(self.target_gt_odom.pose.pose.position.z)
                gt.pose.orientation.w = 1.0
                gt.scale.x = gt.scale.y = gt.scale.z = 0.4
                gt.color.r = 0.0
                gt.color.g = 1.0
                gt.color.b = 0.0
                gt.color.a = 0.9
                gt.lifetime.sec = 1
                marker_array.markers.append(gt)

        self.position_markers_pub.publish(marker_array)

    def publish_ground_truth_error(self, estimated_position: np.ndarray, stamp_ns: int) -> None:
        if self.target_gt_odom is None:
            return

        gt_stamp_ns = stamp_to_ns(self.target_gt_odom.header.stamp)
        if abs(stamp_ns - gt_stamp_ns) > self.max_target_gt_age_ns:
            return

        gt_position = np.array(
            [
                self.target_gt_odom.pose.pose.position.x,
                self.target_gt_odom.pose.pose.position.y,
                self.target_gt_odom.pose.pose.position.z,
            ],
            dtype=np.float64,
        )
        error = estimated_position - gt_position

        sec = stamp_ns // 1_000_000_000
        nanosec = stamp_ns % 1_000_000_000

        error_vector_msg = Vector3Stamped()
        error_vector_msg.header.frame_id = self.target_frame_id
        error_vector_msg.header.stamp.sec = int(sec)
        error_vector_msg.header.stamp.nanosec = int(nanosec)
        error_vector_msg.vector.x = float(error[0])
        error_vector_msg.vector.y = float(error[1])
        error_vector_msg.vector.z = float(error[2])
        self.error_vector_pub.publish(error_vector_msg)

        now = time.time()
        if now - self.last_error_log_time >= 1.0:
            self.get_logger().info(
                'Estimated pos: x=%.3f, y=%.3f, z=%.3f | GT error: dx=%.3f, dy=%.3f, dz=%.3f'
                % (estimated_position[0], estimated_position[1], estimated_position[2], error[0], error[1], error[2])
            )
            self.last_error_log_time = now


def main() -> None:
    rclpy.init()
    node = TestYolov8MultiViewTriangulationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()