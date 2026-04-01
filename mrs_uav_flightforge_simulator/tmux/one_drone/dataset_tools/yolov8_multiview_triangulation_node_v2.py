#!/usr/bin/env python3

import os
import time
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Point, PointStamped, PoseStamped, Vector3Stamped
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
    """State and covariance pair."""
    x: np.ndarray  # state vector  (n,)
    P: np.ndarray  # covariance     (n, n)


class LinearKalmanFilter:
    def __init__(self, A: np.ndarray, B: np.ndarray, H: np.ndarray) -> None:
        self.A = A.copy()
        self.B = B.copy()
        self.H = H.copy()
        self.n = A.shape[0]

    def predict(self, sc: StateCov, u: np.ndarray, Q: np.ndarray, dt: float) -> StateCov:
        x_pred = self.A @ sc.x + self.B @ u
        P_pred = self.A @ sc.P @ self.A.T + Q
        return StateCov(x=x_pred, P=P_pred)

    def correct(self, sc: StateCov, z: np.ndarray, R: np.ndarray) -> StateCov:
        y = z - self.H @ sc.x
        S = self.H @ sc.P @ self.H.T + R
        try:
            K = sc.P @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            K = sc.P @ self.H.T @ np.linalg.pinv(S)
        x_new = sc.x + K @ y
        P_new = (np.eye(self.n) - K @ self.H) @ sc.P
        return StateCov(x=x_new, P=P_new)


def build_transition_matrix_ca(dt: float) -> np.ndarray:
    A = np.eye(9, dtype=np.float64)
    dt2 = 0.5 * dt * dt
    A[0, 3] = dt;  A[0, 6] = dt2
    A[1, 4] = dt;  A[1, 7] = dt2
    A[2, 5] = dt;  A[2, 8] = dt2
    A[3, 6] = dt;  A[4, 7] = dt;  A[5, 8] = dt
    return A


def build_process_noise_ca(dt: float, sigma_a: float) -> np.ndarray:
    dt = float(max(0.01, dt))
    q = float(max(1e-9, sigma_a) ** 2)
    dt2 = dt * dt
    dt3 = dt2 * dt
    dt4 = dt3 * dt
    dt5 = dt4 * dt
    q_block = np.array([
        [dt5 / 20.0, dt4 / 8.0, dt3 / 6.0],
        [dt4 / 8.0,  dt3 / 3.0, dt2 / 2.0],
        [dt3 / 6.0,  dt2 / 2.0, dt],
    ], dtype=np.float64) * q
    Q = np.zeros((9, 9), dtype=np.float64)
    for axis in range(3):
        idx = [axis, axis + 3, axis + 6]
        Q[np.ix_(idx, idx)] = q_block
    return Q


def build_transition_matrix_cv(dt: float) -> np.ndarray:
    A = np.eye(6, dtype=np.float64)
    A[0, 3] = dt;  A[1, 4] = dt;  A[2, 5] = dt
    return A


def build_process_noise_cv(dt: float, sigma_v: float) -> np.ndarray:
    dt = float(max(0.01, dt))
    q = float(max(1e-9, sigma_v) ** 2)
    dt2 = dt * dt
    dt3 = dt2 * dt
    q_block = np.array([
        [dt3 / 3.0, dt2 / 2.0],
        [dt2 / 2.0, dt],
    ], dtype=np.float64) * q
    Q = np.zeros((6, 6), dtype=np.float64)
    for axis in range(3):
        idx = [axis, axis + 3]
        Q[np.ix_(idx, idx)] = q_block
    return Q


def build_transition_matrix_ct(dt: float, omega: float) -> np.ndarray:
    """Non-linear 2D CT (x,y) + linear Z model."""
    A = np.eye(7, dtype=np.float64)
    if abs(omega) < 1e-4:
        # Simplify to CV if turn rate is negligible
        A[0, 3] = dt; A[1, 4] = dt; A[2, 5] = dt
    else:
        sw = math.sin(omega * dt)
        cw = math.cos(omega * dt)
        A[0, 3] = sw / omega
        A[0, 4] = -(1.0 - cw) / omega
        A[1, 3] = (1.0 - cw) / omega
        A[1, 4] = sw / omega
        A[2, 5] = dt
        A[3, 3] = cw
        A[3, 4] = -sw
        A[4, 3] = sw
        A[4, 4] = cw
    return A


def build_process_noise_ct(dt: float, sigma_v: float, sigma_omega: float) -> np.ndarray:
    """Simplified process noise for 7D CT model."""
    Q = np.zeros((7, 7), dtype=np.float64)
    # Block for position/velocity (similar to CV)
    q_cv = build_process_noise_cv(dt, sigma_v)
    Q[:3, :3] = q_cv[:3, :3]
    Q[3:6, 3:6] = q_cv[3:6, 3:6]
    Q[0:3, 3:6] = q_cv[0:3, 3:6]
    Q[3:6, 0:3] = q_cv[3:6, 0:3]
    # Variance for omega
    Q[6, 6] = (sigma_omega ** 2) * dt
    return Q


class IMMFilterV2:
    """IMM filter supporting CV (6D), CA (9D), and CT (7D) models."""
    def __init__(self, pi: np.ndarray, model_probs: np.ndarray):
        self.pi = pi.copy()
        self.mu = model_probs.copy()
        self.n = len(model_probs)
        
        # Model 0: CV
        H0 = np.zeros((3, 6), dtype=np.float64)
        H0[0, 0] = H0[1, 1] = H0[2, 2] = 1.0
        self.kf_cv = LinearKalmanFilter(np.eye(6), np.zeros((6, 1)), H0)
        self.sc_cv: Optional[StateCov] = None
        
        # Model 1: CA
        H1 = np.zeros((3, 9), dtype=np.float64)
        H1[0, 0] = H1[1, 1] = H1[2, 2] = 1.0
        self.kf_ca = LinearKalmanFilter(np.eye(9), np.zeros((9, 1)), H1)
        self.sc_ca: Optional[StateCov] = None
        
        # Model 2: CT
        H2 = np.zeros((3, 7), dtype=np.float64)
        H2[0, 0] = H2[1, 1] = H2[2, 2] = 1.0
        self.kf_ct = LinearKalmanFilter(np.eye(7), np.zeros((7, 1)), H2)
        self.sc_ct: Optional[StateCov] = None

    def initialize(self, measurement: np.ndarray, P_init_diag: float):
        self.sc_cv = StateCov(np.zeros(6), np.eye(6) * P_init_diag)
        self.sc_cv.x[:3] = measurement
        self.sc_ca = StateCov(np.zeros(9), np.eye(9) * P_init_diag)
        self.sc_ca.x[:3] = measurement
        self.sc_ct = StateCov(np.zeros(7), np.eye(7) * P_init_diag)
        self.sc_ct.x[:3] = measurement

    def _state_to_10d(self, x: np.ndarray, model_idx: int) -> np.ndarray:
        """Projects model-specific state to a shared 10D state [p, v, a, omega]."""
        res = np.zeros(10, dtype=np.float64)
        if model_idx == 0: # CV
            res[:6] = x
        elif model_idx == 1: # CA
            res[:9] = x
        elif model_idx == 2: # CT
            res[:6] = x[:6]
            res[9] = x[6]
        return res

    def _state_from_10d(self, x_10d: np.ndarray, model_idx: int) -> np.ndarray:
        if model_idx == 0: return x_10d[:6]
        if model_idx == 1: return x_10d[:9]
        if model_idx == 2:
            res = np.zeros(7)
            res[:6] = x_10d[:6]
            res[6] = x_10d[9]
            return res
        return x_10d

    def _cov_to_10d(self, P: np.ndarray, model_idx: int) -> np.ndarray:
        res = np.eye(10) * 1e-6
        if model_idx == 0: res[:6, :6] = P
        elif model_idx == 1: res[:9, :9] = P
        elif model_idx == 2:
            res[:6, :6] = P[:6, :6]
            res[9, 9] = P[6, 6]
        return res

    def _cov_from_10d(self, P_10d: np.ndarray, model_idx: int) -> np.ndarray:
        if model_idx == 0: return P_10d[:6, :6]
        if model_idx == 1: return P_10d[:9, :9]
        if model_idx == 2:
            res = np.zeros((7, 7))
            res[:6, :6] = P_10d[:6, :6]
            res[6, 6] = P_10d[9, 9]
            return res
        return P_10d

    def predict_and_correct(self, dt: float, Q_cv: np.ndarray, Q_ca: np.ndarray, Q_ct: np.ndarray, z: np.ndarray, R: np.ndarray, mahalanobis_thresh: float = 9.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
        # 1. Mixing
        c_bar = self.pi.T @ self.mu
        mu_mix = np.zeros((self.n, self.n))
        for i in range(self.n):
            for j in range(self.n):
                mu_mix[i, j] = self.pi[i, j] * self.mu[i] / max(c_bar[j], 1e-12)
        
        # Shared 10D Interaction
        states_10d = [self._state_to_10d(s.x, i) for i, s in enumerate([self.sc_cv, self.sc_ca, self.sc_ct])]
        covs_10d = [self._cov_to_10d(s.P, i) for i, s in enumerate([self.sc_cv, self.sc_ca, self.sc_ct])]
        
        x_mix_10d = [np.zeros(10) for _ in range(self.n)]
        P_mix_10d = [np.zeros((10, 10)) for _ in range(self.n)]
        
        for j in range(self.n):
            for i in range(self.n):
                x_mix_10d[j] += states_10d[i] * mu_mix[i, j]
            for i in range(self.n):
                dx = states_10d[i] - x_mix_10d[j]
                P_mix_10d[j] += mu_mix[i, j] * (covs_10d[i] + np.outer(dx, dx))
        
        # Back to models
        self.sc_cv.x = self._state_from_10d(x_mix_10d[0], 0)
        self.sc_cv.P = self._cov_from_10d(P_mix_10d[0], 0)
        self.sc_ca.x = self._state_from_10d(x_mix_10d[1], 1)
        self.sc_ca.P = self._cov_from_10d(P_mix_10d[1], 1)
        self.sc_ct.x = self._state_from_10d(x_mix_10d[2], 2)
        self.sc_ct.P = self._cov_from_10d(P_mix_10d[2], 2)

        # 2. Predict
        self.kf_cv.A = build_transition_matrix_cv(dt)
        self.kf_ca.A = build_transition_matrix_ca(dt)
        self.kf_ct.A = build_transition_matrix_ct(dt, self.sc_ct.x[6])
        
        sc_p_cv = self.kf_cv.predict(self.sc_cv, np.zeros(1), Q_cv, dt)
        sc_p_ca = self.kf_ca.predict(self.sc_ca, np.zeros(1), Q_ca, dt)
        sc_p_ct = self.kf_ct.predict(self.sc_ct, np.zeros(1), Q_ct, dt)
        
        # 3. Gating & Likelihood
        def get_likelihood_and_correct(kf, sc_p, z, R):
            y = z - kf.H @ sc_p.x
            S = kf.H @ sc_p.P @ kf.H.T + R
            try:
                invS = np.linalg.inv(S)
                detS = np.linalg.det(S)
            except np.linalg.LinAlgError:
                invS = np.linalg.pinv(S)
                detS = 1e-6
            
            d2 = float(y.T @ invS @ y)
            # Simplified likelihood (exclude detS to avoid penalizing complex models)
            prob = math.exp(max(-50.0, -0.5 * d2))
            
            # Correct
            if d2 > mahalanobis_thresh:
                return sc_p, prob, False
                
            sc_c = kf.correct(sc_p, z, R)
            return sc_c, prob, True

        self.sc_cv, L_cv, acc_cv = get_likelihood_and_correct(self.kf_cv, sc_p_cv, z, R)
        self.sc_ca, L_ca, acc_ca = get_likelihood_and_correct(self.kf_ca, sc_p_ca, z, R)
        self.sc_ct, L_ct, acc_ct = get_likelihood_and_correct(self.kf_ct, sc_p_ct, z, R)
        
        accepted = acc_cv or acc_ca or acc_ct
        
        if accepted:
            Lambda = np.array([L_cv, L_ca, L_ct])
            self.mu = Lambda * c_bar
            self.mu /= (np.sum(self.mu) + 1e-12)

        # 5. Combination (Full 10D Recombination)
        s_10d = [self._state_to_10d(s.x, i) for i, s in enumerate([self.sc_cv, self.sc_ca, self.sc_ct])]
        c_10d = [self._cov_to_10d(s.P, i) for i, s in enumerate([self.sc_cv, self.sc_ca, self.sc_ct])]
        
        x_comb = np.zeros(10)
        for i in range(self.n): x_comb += s_10d[i] * self.mu[i]
        
        P_comb = np.zeros((10, 10))
        for i in range(self.n):
            dx = s_10d[i] - x_comb
            P_comb += self.mu[i] * (c_10d[i] + np.outer(dx, dx))
            
        return x_comb, P_comb, self.mu, accepted

@dataclass
class DetectionObservation:
    stamp_ns: int
    center_u: float; center_v: float
    confidence: float; class_id: int; class_name: str


class Yolov8MultiViewTriangulationNodeV2(Node):
    def __init__(self) -> None:
        super().__init__('yolov8_multiview_triangulation_node_v2')

        # Parameters (Mostly same as V1)
        self.declare_parameter('observer1_name', 'uav1')
        self.declare_parameter('observer2_name', 'uav2')
        self.declare_parameter('target_name', 'uav3')
        self.declare_parameter('pose_topic', '/target/pose_estimate')
        self.declare_parameter('odometry_topic', '/target/odometry_estimate')
        self.declare_parameter('estimated_position_topic', '/target/position_estimate')
        self.declare_parameter('triangulation_raw_topic', '/target/triangulation_raw')
        self.declare_parameter('error_vector_topic', '/target/position_error')
        self.declare_parameter('target_frame_id', 'world')
        self.declare_parameter('model_path', '~/runs/detect/drone_detector_n_9602/weights/best.pt')
        self.declare_parameter('confidence_threshold', 0.25)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('imgsz', 960)
        self.declare_parameter('max_detections', 100)
        self.declare_parameter('device', 'cuda')
        self.declare_parameter('line_width', 2)
        self.declare_parameter('target_class_id', -1)
        self.declare_parameter('max_pair_age_sec', 0.75)
        self.declare_parameter('triangulation_min_baseline_m', 0.25)
        self.declare_parameter('max_target_gt_age_sec', 0.75)
        self.declare_parameter('processing_rate_hz', 10.0)
        self.declare_parameter('tf_timeout_sec', 0.1)
        self.declare_parameter('world_frame_suffix', 'world_origin')
        
        # Noise parameters
        self.declare_parameter('kf_process_noise_acc', 1.0) 
        self.declare_parameter('kf_process_noise_vel', 1.0) 
        self.declare_parameter('kf_process_noise_omega', 0.8) # High Re-activity
        self.declare_parameter('imm_transition_prob', 0.75)  # Fast switching
        self.declare_parameter('kf_measurement_noise', 0.001) # Very high trust in detections
        self.declare_parameter('dist_ref_m', 30.0) 
        self.declare_parameter('max_triangulation_error_m', 4.0) # Loosened gate
        self.declare_parameter('kf_adaptive_cov_max_multiplier', 50.0)
        self.declare_parameter('kf_initial_covariance', 10.0)
        self.declare_parameter('kf_prediction_horizon_sec', 1.0)
        self.declare_parameter('kf_prediction_steps', 25)

        # Member variables
        self.observer1_name = self.get_parameter('observer1_name').value
        self.observer2_name = self.get_parameter('observer2_name').value
        self.target_name = self.get_parameter('target_name').value
        self.observer_roles = ['observer1', 'observer2']
        self.observer_uav_names = {'observer1': self.observer1_name, 'observer2': self.observer2_name}
        self.target_frame_id = self.get_parameter('target_frame_id').value
        if self.target_frame_id == 'world':
            self.target_frame_id = f'{self.observer1_name}/{self.get_parameter("world_frame_suffix").value}'

        self.bridge = CvBridge()
        self.model = YOLO(os.path.expanduser(self.get_parameter('model_path').value))
        self.model.fuse()

        # State storage
        self.camera_infos: Dict[str, Optional[CameraInfo]] = {r: None for r in self.observer_roles}
        self.observations: Dict[str, Optional[DetectionObservation]] = {r: None for r in self.observer_roles}
        self.latest_images: Dict[str, Optional[Image]] = {r: None for r in self.observer_roles}
        self.last_processed_image_stamp_ns: Dict[str, int] = {r: -1 for r in self.observer_roles}
        self.target_gt_odom: Optional[Odometry] = None

        # IMM V2 Init
        p_stay = 0.90 # More reactive than 0.95
        p_sw = (1.0 - p_stay) / 2.0
        pi = np.array([
            [p_stay, p_sw, p_sw],
            [p_sw, p_stay, p_sw],
            [p_sw, p_sw, p_stay]
        ])
        self.imm = IMMFilterV2(pi, np.array([0.5, 0.25, 0.25]))
        self.imm_initialized = False
        self.imm_last_stamp_ns: Optional[int] = None
        
        # Combined filters results
        self.filtered_position = np.zeros(3)
        self.filtered_velocity = np.zeros(3)
        self.filtered_acceleration = np.zeros(3)
        self.filtered_omega = 0.0
        self.combined_cov_10d = np.eye(10)

        # ROS Comm
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        
        self.detection_pubs = {r: self.create_publisher(Image, f'/{self.observer_uav_names[r]}/detection', 1) for r in self.observer_roles}
        self.pose_pub = self.create_publisher(PoseStamped, self.get_parameter('pose_topic').value, 10)
        self.odometry_pub = self.create_publisher(Odometry, self.get_parameter('odometry_topic').value, 10)
        self.estimated_position_pub = self.create_publisher(Vector3Stamped, self.get_parameter('estimated_position_topic').value, 10)
        self.triangulation_raw_pub = self.create_publisher(PointStamped, self.get_parameter('triangulation_raw_topic').value, 10)
        self.error_vector_pub = self.create_publisher(Vector3Stamped, self.get_parameter('error_vector_topic').value, 10)
        self.predicted_trajectory_pub = self.create_publisher(Path, '/target/predicted_trajectory', 10)
        self.trajectory_markers_pub = self.create_publisher(MarkerArray, '/target/predicted_trajectory_markers', 10)

        for role in self.observer_roles:
            uav = self.observer_uav_names[role]
            self.create_subscription(Image, f'/{uav}/rgb/image_raw', lambda msg, r=role: self.image_cb(r, msg), 1)
            self.create_subscription(CameraInfo, f'/{uav}/rgb/camera_info', lambda msg, r=role: self.info_cb(r, msg), 10)
        
        self.create_subscription(Odometry, f'/{self.target_name}/hw_api/ground_truth', self.gt_cb, 20)
        self.create_timer(1.0 / self.get_parameter('processing_rate_hz').value, self.timer_cb)

        self.get_logger().info("IMM V2 Triangulation Node Started - Featuring Coordinated Turn model")

    def info_cb(self, r, msg): self.camera_infos[r] = msg
    def gt_cb(self, msg): self.target_gt_odom = msg
    def image_cb(self, r, msg): self.latest_images[r] = msg

    def timer_cb(self):
        for role in self.observer_roles:
            img_msg = self.latest_images[role]
            if img_msg and stamp_to_ns(img_msg.header.stamp) > self.last_processed_image_stamp_ns[role]:
                self.last_processed_image_stamp_ns[role] = stamp_to_ns(img_msg.header.stamp)
                self.process_img(role, img_msg)

    def process_img(self, role, msg):
        try:
            cv_img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            res = self.model.predict(cv_img, conf=self.get_parameter('confidence_threshold').value, verbose=False)
            best = self.extract_best(res, msg)
            if best:
                self.observations[role] = best
                self.try_triangulate()
            # Annotation & Publish
            ann = res[0].plot() if res else cv_img
            out = self.bridge.cv2_to_imgmsg(ann, 'bgr8')
            out.header = msg.header
            self.detection_pubs[role].publish(out)
        except Exception as e:
            self.get_logger().error(f"Error processing image: {e}")

    def extract_best(self, res, msg) -> Optional[DetectionObservation]:
        if not res or not res[0].boxes: return None
        box = res[0].boxes[0]
        c = box.xywh[0].tolist()
        return DetectionObservation(stamp_to_ns(msg.header.stamp), c[0], c[1], float(box.conf[0]), int(box.cls[0]), "UAV")

    def try_triangulate(self):
        o1, o2 = self.observations['observer1'], self.observations['observer2']
        i1, i2 = self.camera_infos['observer1'], self.camera_infos['observer2']
        if o1 is None or o2 is None or i1 is None or i2 is None:
            return
            
        if abs(o1.stamp_ns - o2.stamp_ns) > self.get_parameter('max_pair_age_sec').value * 1e9:
            return
        
        r1 = self.get_ray(i1, o1.stamp_ns, o1.center_u, o1.center_v)
        r2 = self.get_ray(i2, o2.stamp_ns, o2.center_u, o2.center_v)
        if not (r1 and r2): return
        
        mid, err = triangulate_midpoint(r1[0], r1[1], r2[0], r2[1])
        if err > self.get_parameter('max_triangulation_error_m').value: return
        
        # --- Distance Based R Scaling ---
        dist = float(np.linalg.norm(mid - r1[0])) # Dist from Observer 1
        d_ref = self.get_parameter('dist_ref_m').value
        r_scale = 1.0 + (dist / d_ref)**2
        
        # Base anisotropic R
        bisector = normalize(r1[1] + r2[1])
        sin_a = np.linalg.norm(np.cross(r1[1], r2[1]))
        var_base = self.get_parameter('kf_measurement_noise').value * r_scale
        var_depth = var_base * min(1.0 / (sin_a + 1e-6), self.get_parameter('kf_adaptive_cov_max_multiplier').value)
        
        E = np.column_stack((bisector, normalize(r1[1]-r2[1]), normalize(np.cross(bisector, r1[1]-r2[1]))))
        R = E @ np.diag([var_depth, var_base, var_base]) @ E.T

        stamp_ns = max(o1.stamp_ns, o2.stamp_ns)
        if not self.imm_initialized:
            self.imm.initialize(mid, self.get_parameter('kf_initial_covariance').value)
            self.imm_initialized = True
            self.imm_last_stamp_ns = stamp_ns
            self.filtered_position = mid
        else:
            dt = (stamp_ns - self.imm_last_stamp_ns) / 1e9
            if dt > 0.005:
                Q_cv = build_process_noise_cv(dt, self.get_parameter('kf_process_noise_vel').value)
                Q_ca = build_process_noise_ca(dt, self.get_parameter('kf_process_noise_acc').value)
                Q_ct = build_process_noise_ct(dt, self.get_parameter('kf_process_noise_vel').value, self.get_parameter('kf_process_noise_omega').value)
                
                x_10d, self.combined_cov_10d, mu, acc = self.imm.predict_and_correct(dt, Q_cv, Q_ca, Q_ct, mid, R)
                
                self.filtered_position = x_10d[:3]
                self.filtered_velocity = x_10d[3:6]
                self.filtered_acceleration = x_10d[6:9]
                self.filtered_omega = x_10d[9]
                self.imm_last_stamp_ns = stamp_ns

        self.publish_all(stamp_ns)

    def get_ray(self, info, t_ns, u, v):
        try:
            ray_opt = normalize(np.array([(u - info.k[2]) / info.k[0], (v - info.k[5]) / info.k[4], 1.0]))
            prefix = info.header.frame_id.split('/')[0]
            tf = self.tf_buffer.lookup_transform(f'{prefix}/{self.get_parameter("world_frame_suffix").value}', info.header.frame_id, Time(nanoseconds=t_ns), Duration(seconds=0.1))
            orig = np.array([tf.transform.translation.x, tf.transform.translation.y, tf.transform.translation.z])
            rot = quat_to_rotmat(tf.transform.rotation.x, tf.transform.rotation.y, tf.transform.rotation.z, tf.transform.rotation.w)
            return orig, normalize(rot @ ray_opt)
        except: return None

    def publish_all(self, stamp_ns):
        t = Time(nanoseconds=stamp_ns).to_msg()
        # Pose
        ps = PoseStamped()
        ps.header.stamp, ps.header.frame_id = t, self.target_frame_id
        ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = self.filtered_position.tolist()
        ps.pose.orientation.w = 1.0
        self.pose_pub.publish(ps)

        # Vector3Stamped (Required by some evaluation tools)
        vs = Vector3Stamped()
        vs.header = ps.header
        vs.vector.x, vs.vector.y, vs.vector.z = ps.pose.position.x, ps.pose.position.y, ps.pose.position.z
        self.estimated_position_pub.publish(vs)

        # Odom
        o = Odometry(); o.header = ps.header; o.pose.pose = ps.pose
        o.twist.twist.linear.x, o.twist.twist.linear.y, o.twist.twist.linear.z = self.filtered_velocity.tolist()
        P = self.combined_cov_10d
        o.pose.covariance[0], o.pose.covariance[7], o.pose.covariance[14] = float(P[0,0]), float(P[1,1]), float(P[2,2])
        # Twist covariance
        o.twist.covariance[0], o.twist.covariance[7], o.twist.covariance[14] = float(P[3,3]), float(P[4,4]), float(P[5,5])
        self.odometry_pub.publish(o)

        # Trajectory & Markers
        self._pub_traj(stamp_ns)
        self._pub_markers(ps.pose.position, stamp_ns)

    def _pub_traj(self, stamp_ns):
        t_msg = Time(nanoseconds=stamp_ns).to_msg()
        path = Path(); path.header.stamp, path.header.frame_id = t_msg, self.target_frame_id
        
        horizon = self.get_parameter('kf_prediction_horizon_sec').value
        steps = int(self.get_parameter('kf_prediction_steps').value)
        dt = horizon / max(1, steps)
        
        mu_static = self.imm.mu
        x_cv, x_ca, x_ct = self.imm.sc_cv.x.copy(), self.imm.sc_ca.x.copy(), self.imm.sc_ct.x.copy()
        
        pred_points = []
        for i in range(steps + 1):
            p_cv, p_ca, p_ct = x_cv[:3], x_ca[:3], x_ct[:3]
            pos = p_cv * mu_static[0] + p_ca * mu_static[1] + p_ct * mu_static[2]
            pred_points.append(pos)
            
            # Message Poses
            ps = PoseStamped()
            ps.header.frame_id = self.target_frame_id
            ps.header.stamp = Time(nanoseconds=stamp_ns + int(i * dt * 1e9)).to_msg()
            ps.pose.position.x, ps.pose.position.y, ps.pose.position.z = pos.tolist()
            ps.pose.orientation.w = 1.0
            path.poses.append(ps)
            
            # Predict
            x_cv = build_transition_matrix_cv(dt) @ x_cv
            x_ca = build_transition_matrix_ca(dt) @ x_ca
            x_ct = build_transition_matrix_ct(dt, x_ct[6]) @ x_ct
            
        self.predicted_trajectory_pub.publish(path)

        # --- ARROW MARKERS ---
        ma = MarkerArray()
        # Clear old
        c = Marker(); c.header.frame_id, c.ns, c.action = self.target_frame_id, 'traj', Marker.DELETEALL
        ma.markers.append(c)

        for i in range(len(pred_points)-1):
            alpha = i / max(1, len(pred_points)-2)
            m = Marker()
            m.header.frame_id, m.header.stamp = self.target_frame_id, t_msg
            m.ns, m.id, m.type, m.action = 'traj', i, Marker.ARROW, Marker.ADD
            m.scale.x, m.scale.y, m.scale.z = 0.05, 0.1, 0.0
            m.color.r, m.color.g, m.color.b, m.color.a = 1.0, float(1.0-alpha), 0.0, float(0.8-0.4*alpha)
            m.points = [Point(x=float(pred_points[i][0]), y=float(pred_points[i][1]), z=float(pred_points[i][2])),
                        Point(x=float(pred_points[i+1][0]), y=float(pred_points[i+1][1]), z=float(pred_points[i+1][2]))]
            ma.markers.append(m)
        self.trajectory_markers_pub.publish(ma)

    def _pub_markers(self, pos, stamp_ns):
        t_msg = Time(nanoseconds=stamp_ns).to_msg()
        ma = MarkerArray()
        # Est Sphere
        m = Marker()
        m.header.frame_id, m.header.stamp = self.target_frame_id, t_msg
        m.ns, m.id, m.type, m.action = 'est_pos', 0, Marker.SPHERE, Marker.ADD
        m.pose.position.x, m.pose.position.y, m.pose.position.z = float(pos.x), float(pos.y), float(pos.z)
        m.scale.x = m.scale.y = m.scale.z = 0.4
        m.color.r, m.color.g, m.color.b, m.color.a = 0.0, 0.4, 1.0, 0.9
        ma.markers.append(m)
        
        # GT Sphere (if available)
        gt_odom = self.target_gt_odom
        if gt_odom is not None:
            gt_pos = gt_odom.pose.pose.position
            m2 = Marker()
            m2.header.frame_id, m2.header.stamp = self.target_frame_id, t_msg
            m2.ns, m2.id, m2.type, m2.action = 'gt_pos', 1, Marker.SPHERE, Marker.ADD
            m2.pose.position.x, m2.pose.position.y, m2.pose.position.z = float(gt_pos.x), float(gt_pos.y), float(gt_pos.z)
            m2.scale.x = m2.scale.y = m2.scale.z = 0.4
            m2.color.r, m2.color.g, m2.color.b, m2.color.a = 0.0, 1.0, 0.0, 0.9
            ma.markers.append(m2)
            
        self.trajectory_markers_pub.publish(ma) # Reusing this for simplicity or create another




def main():
    rclpy.init()
    node = Yolov8MultiViewTriangulationNodeV2()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
