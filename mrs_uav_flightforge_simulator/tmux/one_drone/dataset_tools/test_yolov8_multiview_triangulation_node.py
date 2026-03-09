#!/usr/bin/env python3

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import PoseStamped, Vector3Stamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
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


def rpy_to_rotmat(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)

    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]], dtype=np.float64)
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]], dtype=np.float64)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return rz @ ry @ rx


def stamp_to_ns(stamp) -> int:
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm <= 1e-9:
        raise ValueError('Cannot normalize near-zero vector')
    return vec / norm


def optical_to_camera_ray(ray_optical: np.ndarray) -> np.ndarray:
    return np.array([ray_optical[2], -ray_optical[0], -ray_optical[1]], dtype=np.float64)


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

        self.declare_parameter('uav1_image_topic', '/uav1/rgb/image_raw')
        self.declare_parameter('uav2_image_topic', '/uav2/rgb/image_raw')
        self.declare_parameter('uav1_detection_topic', '/uav1/detection')
        self.declare_parameter('uav2_detection_topic', '/uav2/detection')
        self.declare_parameter('uav1_camera_info_topic', '/uav1/rgb/camera_info')
        self.declare_parameter('uav2_camera_info_topic', '/uav2/rgb/camera_info')
        self.declare_parameter('uav1_odom_topic', '/uav1/hw_api/ground_truth')
        self.declare_parameter('uav2_odom_topic', '/uav2/hw_api/ground_truth')
        self.declare_parameter('target_gt_odom_topic', '/uav3/hw_api/ground_truth')
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
        self.declare_parameter('max_pose_age_sec', 0.75)
        self.declare_parameter('triangulation_min_baseline_m', 0.25)
        self.declare_parameter('max_triangulation_error_m', 2.0)
        self.declare_parameter('max_target_gt_age_sec', 0.75)
        self.declare_parameter('processing_rate_hz', 5.0)
        self.declare_parameter('camera_offset_xyz_m', [0.118, 0.0, 0.016])
        self.declare_parameter('camera_rpy_deg', [0.0, 0.0, 0.0])
        self.declare_parameter('use_body_to_optical_conversion', True)

        self.uav1_image_topic = str(self.get_parameter('uav1_image_topic').value)
        self.uav2_image_topic = str(self.get_parameter('uav2_image_topic').value)
        self.uav1_detection_topic = str(self.get_parameter('uav1_detection_topic').value)
        self.uav2_detection_topic = str(self.get_parameter('uav2_detection_topic').value)
        self.uav1_camera_info_topic = str(self.get_parameter('uav1_camera_info_topic').value)
        self.uav2_camera_info_topic = str(self.get_parameter('uav2_camera_info_topic').value)
        self.uav1_odom_topic = str(self.get_parameter('uav1_odom_topic').value)
        self.uav2_odom_topic = str(self.get_parameter('uav2_odom_topic').value)
        self.target_gt_odom_topic = str(self.get_parameter('target_gt_odom_topic').value)
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
        self.max_pose_age_ns = int(float(self.get_parameter('max_pose_age_sec').value) * 1_000_000_000.0)
        self.triangulation_min_baseline_m = float(self.get_parameter('triangulation_min_baseline_m').value)
        self.max_triangulation_error_m = float(self.get_parameter('max_triangulation_error_m').value)
        self.max_target_gt_age_ns = int(float(self.get_parameter('max_target_gt_age_sec').value) * 1_000_000_000.0)
        self.processing_rate_hz = max(0.5, float(self.get_parameter('processing_rate_hz').value))
        self.use_body_to_optical = bool(self.get_parameter('use_body_to_optical_conversion').value)

        camera_offset_xyz = self.get_parameter('camera_offset_xyz_m').value
        if len(camera_offset_xyz) != 3:
            raise ValueError('camera_offset_xyz_m must contain 3 values [x, y, z]')
        self.t_bc = np.array(camera_offset_xyz, dtype=np.float64)

        camera_rpy_deg = self.get_parameter('camera_rpy_deg').value
        if len(camera_rpy_deg) != 3:
            raise ValueError('camera_rpy_deg must contain 3 values [roll, pitch, yaw]')
        roll, pitch, yaw = [np.deg2rad(float(v)) for v in camera_rpy_deg]
        self.r_bc = rpy_to_rotmat(roll, pitch, yaw)

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f'Model not found: {self.model_path}')

        self.bridge = CvBridge()
        self.model = YOLO(self.model_path)
        self.model.fuse()

        self.camera_infos: Dict[str, Optional[CameraInfo]] = {'uav1': None, 'uav2': None}
        self.odometries: Dict[str, Optional[Odometry]] = {'uav1': None, 'uav2': None}
        self.observations: Dict[str, Optional[DetectionObservation]] = {'uav1': None, 'uav2': None}
        self.latest_images: Dict[str, Optional[Image]] = {'uav1': None, 'uav2': None}
        self.last_processed_image_stamp_ns: Dict[str, int] = {'uav1': -1, 'uav2': -1}
        self.target_gt_odom: Optional[Odometry] = None

        self.last_pose_ns: Optional[int] = None
        self.last_pose_position: Optional[np.ndarray] = None
        self.last_error_log_time = time.time()
        self.frame_counter = 0
        self.last_log_time = time.time()

        self.uav1_detection_pub = self.create_publisher(Image, self.uav1_detection_topic, 10)
        self.uav2_detection_pub = self.create_publisher(Image, self.uav2_detection_topic, 10)
        self.pose_pub = self.create_publisher(PoseStamped, self.pose_topic, 10)
        self.odometry_pub = self.create_publisher(Odometry, self.odometry_topic, 10)
        self.estimated_position_pub = self.create_publisher(Vector3Stamped, self.estimated_position_topic, 10)
        self.error_vector_pub = self.create_publisher(Vector3Stamped, self.error_vector_topic, 10)

        self.create_subscription(Image, self.uav1_image_topic, self.uav1_image_callback, 1)
        self.create_subscription(Image, self.uav2_image_topic, self.uav2_image_callback, 1)
        self.create_subscription(CameraInfo, self.uav1_camera_info_topic, lambda msg: self.camera_info_callback('uav1', msg), 10)
        self.create_subscription(CameraInfo, self.uav2_camera_info_topic, lambda msg: self.camera_info_callback('uav2', msg), 10)
        self.create_subscription(Odometry, self.uav1_odom_topic, lambda msg: self.odom_callback('uav1', msg), 20)
        self.create_subscription(Odometry, self.uav2_odom_topic, lambda msg: self.odom_callback('uav2', msg), 20)
        self.create_subscription(Odometry, self.target_gt_odom_topic, self.target_gt_odom_callback, 20)
        self.create_timer(1.0 / self.processing_rate_hz, self.processing_timer_callback)

        self.get_logger().info(f'YOLO model path: {self.model_path}')
        self.get_logger().info(f'uav1 image: {self.uav1_image_topic} -> {self.uav1_detection_topic}')
        self.get_logger().info(f'uav2 image: {self.uav2_image_topic} -> {self.uav2_detection_topic}')
        self.get_logger().info(f'uav1 odom: {self.uav1_odom_topic}')
        self.get_logger().info(f'uav2 odom: {self.uav2_odom_topic}')
        self.get_logger().info(f'target GT odom: {self.target_gt_odom_topic}')
        self.get_logger().info(f'Pose topic: {self.pose_topic}')
        self.get_logger().info(f'Odometry topic: {self.odometry_topic}')
        self.get_logger().info(f'Estimated position topic: {self.estimated_position_topic}')
        self.get_logger().info(f'Error vector topic: {self.error_vector_topic}')
        self.get_logger().info(f'Processing rate: {self.processing_rate_hz:.1f} Hz')

    def camera_info_callback(self, uav_name: str, msg: CameraInfo) -> None:
        self.camera_infos[uav_name] = msg

    def odom_callback(self, uav_name: str, msg: Odometry) -> None:
        self.odometries[uav_name] = msg

    def target_gt_odom_callback(self, msg: Odometry) -> None:
        self.target_gt_odom = msg

    def uav1_image_callback(self, msg: Image) -> None:
        self.latest_images['uav1'] = msg

    def uav2_image_callback(self, msg: Image) -> None:
        self.latest_images['uav2'] = msg

    def processing_timer_callback(self) -> None:
        self.process_latest_image('uav1', self.uav1_detection_pub)
        self.process_latest_image('uav2', self.uav2_detection_pub)

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
        obs1 = self.observations['uav1']
        obs2 = self.observations['uav2']
        info1 = self.camera_infos['uav1']
        info2 = self.camera_infos['uav2']
        odom1 = self.odometries['uav1']
        odom2 = self.odometries['uav2']

        if obs1 is None or obs2 is None or info1 is None or info2 is None or odom1 is None or odom2 is None:
            return

        if abs(obs1.stamp_ns - obs2.stamp_ns) > self.max_pair_age_ns:
            return

        odom1_age = abs(obs1.stamp_ns - stamp_to_ns(odom1.header.stamp))
        odom2_age = abs(obs2.stamp_ns - stamp_to_ns(odom2.header.stamp))
        if odom1_age > self.max_pose_age_ns or odom2_age > self.max_pose_age_ns:
            return

        origin1, dir1 = self.pixel_to_world_ray(info1, odom1, obs1.center_u, obs1.center_v)
        origin2, dir2 = self.pixel_to_world_ray(info2, odom2, obs2.center_u, obs2.center_v)

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
        self.publish_pose_estimate(midpoint, stamp_ns)
        self.publish_ground_truth_error(midpoint, stamp_ns)

    def pixel_to_world_ray(
        self,
        camera_info: CameraInfo,
        odom: Odometry,
        u: float,
        v: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        fx = float(camera_info.k[0])
        fy = float(camera_info.k[4])
        cx = float(camera_info.k[2])
        cy = float(camera_info.k[5])

        ray_optical = normalize(np.array([(u - cx) / fx, (v - cy) / fy, 1.0], dtype=np.float64))
        if self.use_body_to_optical:
            ray_camera = optical_to_camera_ray(ray_optical)
        else:
            ray_camera = ray_optical

        pose = odom.pose.pose
        position_world = np.array([pose.position.x, pose.position.y, pose.position.z], dtype=np.float64)
        r_wb = quat_to_rotmat(pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w)

        camera_origin_world = position_world + r_wb @ self.t_bc
        ray_body = self.r_bc @ ray_camera
        ray_world = normalize(r_wb @ ray_body)
        return camera_origin_world, ray_world

    def publish_pose_estimate(self, position: np.ndarray, stamp_ns: int) -> None:
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

        odom_msg = Odometry()
        odom_msg.header = pose_msg.header
        odom_msg.child_frame_id = 'target_estimate'
        odom_msg.pose.pose = pose_msg.pose
        odom_msg.pose.covariance[0] = 0.25
        odom_msg.pose.covariance[7] = 0.25
        odom_msg.pose.covariance[14] = 0.25

        if self.last_pose_ns is not None and self.last_pose_position is not None and stamp_ns > self.last_pose_ns:
            dt = (stamp_ns - self.last_pose_ns) / 1_000_000_000.0
            if 1e-3 < dt < 1.0:
                velocity = (position - self.last_pose_position) / dt
                odom_msg.twist.twist.linear.x = float(velocity[0])
                odom_msg.twist.twist.linear.y = float(velocity[1])
                odom_msg.twist.twist.linear.z = float(velocity[2])

        self.odometry_pub.publish(odom_msg)
        self.last_pose_ns = stamp_ns
        self.last_pose_position = position.copy()

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