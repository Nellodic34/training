#!/usr/bin/env python3

import csv
import os
import random
from datetime import datetime
from typing import Optional, Tuple

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image


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


def quat_to_yaw(x: float, y: float, z: float, w: float) -> float:
    return float(np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))


def rpy_to_rotmat(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)

    rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]], dtype=np.float64)
    ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]], dtype=np.float64)
    rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return rz @ ry @ rx


def wrap_angle(angle_rad: float) -> float:
    return float((angle_rad + np.pi) % (2.0 * np.pi) - np.pi)


def stamp_to_ns(stamp) -> int:
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


class CollectHeadingDatasetNode(Node):
    def __init__(self) -> None:
        super().__init__('collect_heading_dataset_node')

        self.declare_parameter('rgb_topic', '/uav1/rgb/image_raw')
        self.declare_parameter('camera_info_topic', '/uav1/rgb/camera_info')
        self.declare_parameter('depth_topic', '/uav1/depth/image_raw')
        self.declare_parameter('observer_odom_topic', '/uav1/hw_api/ground_truth')
        self.declare_parameter('target_odom_topic', '/uav3/hw_api/ground_truth')
        self.declare_parameter('output_dir', os.path.expanduser('~/dataset_uav_heading'))
        self.declare_parameter('sample_every_n_frames', 5)
        self.declare_parameter('target_diameter_m', 0.7)
        self.declare_parameter('bbox_scale', 1.25)
        self.declare_parameter('min_bbox_size_px', 12.0)
        self.declare_parameter('max_bbox_size_px', 700.0)
        self.declare_parameter('crop_expand_scale', 1.2)
        self.declare_parameter('save_full_image', False)
        self.declare_parameter('occlusion_check_enabled', True)
        self.declare_parameter('occlusion_margin_m', 0.35)
        self.declare_parameter('max_depth_age_sec', 0.2)
        self.declare_parameter('invalid_depth_is_occluded', False)
        self.declare_parameter('max_pose_age_sec', 0.2)
        self.declare_parameter('camera_offset_xyz_m', [0.118, 0.0, 0.016])
        self.declare_parameter('camera_rpy_deg', [0.0, 0.0, 0.0])
        self.declare_parameter('use_body_to_optical_conversion', True)
        self.declare_parameter('train_split', 0.9)
        self.declare_parameter('random_seed', 42)
        self.declare_parameter('jpeg_quality', 95)
        self.declare_parameter('debug_labeled_images', True)
        self.declare_parameter('debug_output_dir', '/home/nello/data_test_heading')

        rgb_topic = str(self.get_parameter('rgb_topic').value)
        camera_info_topic = str(self.get_parameter('camera_info_topic').value)
        depth_topic = str(self.get_parameter('depth_topic').value)
        observer_odom_topic = str(self.get_parameter('observer_odom_topic').value)
        target_odom_topic = str(self.get_parameter('target_odom_topic').value)
        self.base_output_dir = str(self.get_parameter('output_dir').value)

        self.sample_every_n_frames = max(1, int(self.get_parameter('sample_every_n_frames').value))
        self.target_diameter_m = float(self.get_parameter('target_diameter_m').value)
        self.bbox_scale = float(self.get_parameter('bbox_scale').value)
        self.min_bbox_size_px = float(self.get_parameter('min_bbox_size_px').value)
        self.max_bbox_size_px = float(self.get_parameter('max_bbox_size_px').value)
        self.crop_expand_scale = max(1.0, float(self.get_parameter('crop_expand_scale').value))
        self.save_full_image = bool(self.get_parameter('save_full_image').value)

        self.occlusion_check_enabled = bool(self.get_parameter('occlusion_check_enabled').value)
        self.occlusion_margin_m = float(self.get_parameter('occlusion_margin_m').value)
        self.max_depth_age_sec = float(self.get_parameter('max_depth_age_sec').value)
        self.invalid_depth_is_occluded = bool(self.get_parameter('invalid_depth_is_occluded').value)
        self.max_pose_age_sec = float(self.get_parameter('max_pose_age_sec').value)
        self.use_body_to_optical = bool(self.get_parameter('use_body_to_optical_conversion').value)
        self.train_split = float(self.get_parameter('train_split').value)
        self.rng = random.Random(int(self.get_parameter('random_seed').value))
        self.jpeg_quality = int(self.get_parameter('jpeg_quality').value)
        self.debug_labeled_images = bool(self.get_parameter('debug_labeled_images').value)
        self.base_debug_output_dir = str(self.get_parameter('debug_output_dir').value)

        self.run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_dir = os.path.join(self.base_output_dir, self.run_id)
        self.debug_output_dir = os.path.join(self.base_debug_output_dir, self.run_id)

        camera_offset_xyz = self.get_parameter('camera_offset_xyz_m').value
        if len(camera_offset_xyz) != 3:
            raise ValueError('camera_offset_xyz_m must contain 3 values [x, y, z]')
        self.t_bc = np.array(camera_offset_xyz, dtype=np.float64)

        camera_rpy_deg = self.get_parameter('camera_rpy_deg').value
        if len(camera_rpy_deg) != 3:
            raise ValueError('camera_rpy_deg must contain 3 values [roll, pitch, yaw]')
        roll, pitch, yaw = [np.deg2rad(float(v)) for v in camera_rpy_deg]
        self.r_bc = rpy_to_rotmat(roll, pitch, yaw)

        self.bridge = CvBridge()
        self.frame_count = 0
        self.saved_count = 0
        self.skipped_count = 0
        self.occluded_count = 0
        self.depth_stale_count = 0
        self.depth_invalid_count = 0
        self.depth_missing_warned = False

        self.latest_camera_info: Optional[CameraInfo] = None
        self.latest_observer_odom: Optional[Odometry] = None
        self.latest_target_odom: Optional[Odometry] = None
        self.latest_depth: Optional[np.ndarray] = None
        self.latest_depth_stamp_ns: Optional[int] = None

        self.crops_train_dir = os.path.join(self.output_dir, 'crops', 'train')
        self.crops_val_dir = os.path.join(self.output_dir, 'crops', 'val')
        self.labels_train_dir = os.path.join(self.output_dir, 'labels', 'train')
        self.labels_val_dir = os.path.join(self.output_dir, 'labels', 'val')
        self.images_train_dir = os.path.join(self.output_dir, 'images', 'train')
        self.images_val_dir = os.path.join(self.output_dir, 'images', 'val')

        paths = [self.crops_train_dir, self.crops_val_dir, self.labels_train_dir, self.labels_val_dir]
        if self.save_full_image:
            paths += [self.images_train_dir, self.images_val_dir]
        for path in paths:
            os.makedirs(path, exist_ok=True)

        self.metadata_path = os.path.join(self.output_dir, 'metadata.csv')
        self._init_metadata_csv()

        if self.debug_labeled_images:
            self.debug_train_dir = os.path.join(self.debug_output_dir, 'train')
            self.debug_val_dir = os.path.join(self.debug_output_dir, 'val')
            os.makedirs(self.debug_train_dir, exist_ok=True)
            os.makedirs(self.debug_val_dir, exist_ok=True)
        else:
            self.debug_train_dir = ''
            self.debug_val_dir = ''

        self.create_subscription(Image, rgb_topic, self.rgb_callback, 10)
        self.create_subscription(CameraInfo, camera_info_topic, self.camera_info_callback, 10)
        self.create_subscription(Image, depth_topic, self.depth_callback, 10)
        self.create_subscription(Odometry, observer_odom_topic, self.observer_odom_callback, 30)
        self.create_subscription(Odometry, target_odom_topic, self.target_odom_callback, 30)

        self.get_logger().info(f'Listening RGB: {rgb_topic}')
        self.get_logger().info(f'Listening camera_info: {camera_info_topic}')
        self.get_logger().info(f'Listening depth: {depth_topic}')
        self.get_logger().info(f'Listening observer GT: {observer_odom_topic}')
        self.get_logger().info(f'Listening target GT: {target_odom_topic}')
        self.get_logger().info(f'Run id: {self.run_id}')
        self.get_logger().info(f'Saving heading dataset to: {self.output_dir} (base: {self.base_output_dir})')
        if self.debug_labeled_images:
            self.get_logger().info(f'Saving debug labeled images to: {self.debug_output_dir} (base: {self.base_debug_output_dir})')

    def _init_metadata_csv(self) -> None:
        os.makedirs(self.output_dir, exist_ok=True)
        with open(self.metadata_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                'sample_id',
                'split',
                'stamp_ns',
                'crop_relpath',
                'label_relpath',
                'image_relpath',
                'bbox_x1',
                'bbox_y1',
                'bbox_x2',
                'bbox_y2',
                'bbox_cx',
                'bbox_cy',
                'bbox_w',
                'bbox_h',
                'yaw_world_rad',
                'yaw_relative_world_rad',
                'yaw_camera_rad',
                'sin_yaw_camera',
                'cos_yaw_camera',
            ])

    def camera_info_callback(self, msg: CameraInfo) -> None:
        self.latest_camera_info = msg

    def observer_odom_callback(self, msg: Odometry) -> None:
        self.latest_observer_odom = msg

    def target_odom_callback(self, msg: Odometry) -> None:
        self.latest_target_odom = msg

    def depth_callback(self, msg: Image) -> None:
        try:
            self.latest_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            self.latest_depth_stamp_ns = stamp_to_ns(msg.header.stamp)
        except Exception:
            self.latest_depth = None
            self.latest_depth_stamp_ns = None

    def project_target_center(
        self,
        camera_info: CameraInfo,
        observer_odom: Odometry,
        target_odom: Odometry,
    ) -> Optional[Tuple[float, float, float, float]]:
        fx = float(camera_info.k[0])
        fy = float(camera_info.k[4])
        cx = float(camera_info.k[2])
        cy = float(camera_info.k[5])

        obs_pos = observer_odom.pose.pose.position
        obs_ori = observer_odom.pose.pose.orientation
        tgt_pos = target_odom.pose.pose.position

        p_obs_w = np.array([obs_pos.x, obs_pos.y, obs_pos.z], dtype=np.float64)
        p_tgt_w = np.array([tgt_pos.x, tgt_pos.y, tgt_pos.z], dtype=np.float64)

        r_wb = quat_to_rotmat(obs_ori.x, obs_ori.y, obs_ori.z, obs_ori.w)
        r_bw = r_wb.T

        p_tgt_b = r_bw @ (p_tgt_w - p_obs_w)
        p_tgt_cam = self.r_bc.T @ (p_tgt_b - self.t_bc)

        if self.use_body_to_optical:
            p_opt = np.array([-p_tgt_cam[1], -p_tgt_cam[2], p_tgt_cam[0]], dtype=np.float64)
        else:
            p_opt = p_tgt_cam

        depth = float(p_opt[2])
        if depth <= 0.2:
            return None

        u = fx * (p_opt[0] / depth) + cx
        v = fy * (p_opt[1] / depth) + cy

        if not np.isfinite(u) or not np.isfinite(v):
            return None

        return (u, v, depth, fx)

    def center_to_bbox_px(
        self,
        u: float,
        v: float,
        depth: float,
        fx: float,
        image_width: int,
        image_height: int,
    ) -> Optional[Tuple[int, int, int, int]]:
        bbox_size_px = self.bbox_scale * fx * self.target_diameter_m / depth
        bbox_size_px = max(self.min_bbox_size_px, min(self.max_bbox_size_px, bbox_size_px))
        half = 0.5 * bbox_size_px

        x1 = int(max(0.0, u - half))
        y1 = int(max(0.0, v - half))
        x2 = int(min(float(image_width - 1), u + half))
        y2 = int(min(float(image_height - 1), v + half))

        w_px = x2 - x1
        h_px = y2 - y1
        if w_px <= 2 or h_px <= 2:
            return None

        return (x1, y1, x2, y2)

    def expand_bbox(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        image_width: int,
        image_height: int,
    ) -> Tuple[int, int, int, int]:
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        w = (x2 - x1) * self.crop_expand_scale
        h = (y2 - y1) * self.crop_expand_scale

        ex1 = int(max(0, round(cx - 0.5 * w)))
        ey1 = int(max(0, round(cy - 0.5 * h)))
        ex2 = int(min(image_width - 1, round(cx + 0.5 * w)))
        ey2 = int(min(image_height - 1, round(cy + 0.5 * h)))

        if ex2 <= ex1:
            ex2 = min(image_width - 1, ex1 + 1)
        if ey2 <= ey1:
            ey2 = min(image_height - 1, ey1 + 1)
        return ex1, ey1, ex2, ey2

    def depth_at_pixel_m(self, u: float, v: float) -> Optional[float]:
        if self.latest_depth is None:
            return None

        depth_img = self.latest_depth
        if depth_img.ndim != 2:
            return None

        h, w = depth_img.shape
        x = int(np.clip(round(u), 0, w - 1))
        y = int(np.clip(round(v), 0, h - 1))
        value = depth_img[y, x]

        if np.issubdtype(depth_img.dtype, np.integer):
            depth_m = float(value) / 1000.0
        else:
            depth_m = float(value)

        if not np.isfinite(depth_m) or depth_m <= 0.0:
            return None

        return depth_m

    def is_target_occluded(self, image_stamp_ns: int, u: float, v: float, target_depth_m: float) -> bool:
        if not self.occlusion_check_enabled:
            return False

        if self.latest_depth is None or self.latest_depth_stamp_ns is None:
            if not self.depth_missing_warned:
                self.get_logger().warn('Depth topic not received yet, occlusion check is temporarily bypassed')
                self.depth_missing_warned = True
            return False

        max_depth_age_ns = int(self.max_depth_age_sec * 1_000_000_000.0)
        if abs(image_stamp_ns - self.latest_depth_stamp_ns) > max_depth_age_ns:
            self.depth_stale_count += 1
            return False

        depth_m = self.depth_at_pixel_m(u, v)
        if depth_m is None:
            self.depth_invalid_count += 1
            return self.invalid_depth_is_occluded

        return (depth_m + self.occlusion_margin_m) < target_depth_m

    def compute_heading_labels(self, observer_odom: Odometry, target_odom: Odometry) -> Tuple[float, float, float, float, float]:
        obs_q = observer_odom.pose.pose.orientation
        tgt_q = target_odom.pose.pose.orientation

        yaw_obs_world = quat_to_yaw(obs_q.x, obs_q.y, obs_q.z, obs_q.w)
        yaw_tgt_world = quat_to_yaw(tgt_q.x, tgt_q.y, tgt_q.z, tgt_q.w)
        yaw_relative_world = wrap_angle(yaw_tgt_world - yaw_obs_world)

        r_wb_obs = quat_to_rotmat(obs_q.x, obs_q.y, obs_q.z, obs_q.w)
        r_bw_obs = r_wb_obs.T
        r_wb_tgt = quat_to_rotmat(tgt_q.x, tgt_q.y, tgt_q.z, tgt_q.w)

        forward_world = r_wb_tgt[:, 0]
        forward_body_obs = r_bw_obs @ forward_world
        forward_cam = self.r_bc.T @ forward_body_obs

        if self.use_body_to_optical:
            forward_opt = np.array([-forward_cam[1], -forward_cam[2], forward_cam[0]], dtype=np.float64)
        else:
            forward_opt = forward_cam

        yaw_camera = wrap_angle(float(np.arctan2(forward_opt[0], forward_opt[2])))
        return yaw_tgt_world, yaw_relative_world, yaw_camera, float(np.sin(yaw_camera)), float(np.cos(yaw_camera))

    def append_metadata_row(
        self,
        sample_id: str,
        split: str,
        stamp_ns: int,
        crop_relpath: str,
        label_relpath: str,
        image_relpath: str,
        bbox_px: Tuple[int, int, int, int],
        yaw_world: float,
        yaw_rel_world: float,
        yaw_cam: float,
        sin_yaw_cam: float,
        cos_yaw_cam: float,
    ) -> None:
        x1, y1, x2, y2 = bbox_px
        bw = x2 - x1
        bh = y2 - y1
        bcx = x1 + 0.5 * bw
        bcy = y1 + 0.5 * bh

        with open(self.metadata_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                sample_id,
                split,
                stamp_ns,
                crop_relpath,
                label_relpath,
                image_relpath,
                x1,
                y1,
                x2,
                y2,
                bcx,
                bcy,
                bw,
                bh,
                yaw_world,
                yaw_rel_world,
                yaw_cam,
                sin_yaw_cam,
                cos_yaw_cam,
            ])

    def rgb_callback(self, rgb_msg: Image) -> None:
        self.frame_count += 1

        if self.frame_count % self.sample_every_n_frames != 0:
            return

        if self.latest_camera_info is None or self.latest_observer_odom is None or self.latest_target_odom is None:
            self.skipped_count += 1
            return

        image_stamp_ns = stamp_to_ns(rgb_msg.header.stamp)
        observer_stamp_ns = stamp_to_ns(self.latest_observer_odom.header.stamp)
        target_stamp_ns = stamp_to_ns(self.latest_target_odom.header.stamp)

        max_age_ns = int(self.max_pose_age_sec * 1_000_000_000.0)
        if abs(image_stamp_ns - observer_stamp_ns) > max_age_ns or abs(image_stamp_ns - target_stamp_ns) > max_age_ns:
            self.skipped_count += 1
            return

        rgb = self.bridge.imgmsg_to_cv2(rgb_msg, desired_encoding='bgr8')
        height, width = rgb.shape[:2]

        projection = self.project_target_center(
            camera_info=self.latest_camera_info,
            observer_odom=self.latest_observer_odom,
            target_odom=self.latest_target_odom,
        )
        if projection is None:
            self.skipped_count += 1
            return

        u, v, target_depth_m, fx = projection
        bbox = self.center_to_bbox_px(u, v, target_depth_m, fx, width, height)
        if bbox is None:
            self.skipped_count += 1
            return

        if self.is_target_occluded(image_stamp_ns, u, v, target_depth_m):
            self.occluded_count += 1
            self.skipped_count += 1
            return

        yaw_world, yaw_rel_world, yaw_cam, sin_yaw_cam, cos_yaw_cam = self.compute_heading_labels(
            observer_odom=self.latest_observer_odom,
            target_odom=self.latest_target_odom,
        )

        split = 'train' if self.rng.random() < self.train_split else 'val'
        crop_dir = self.crops_train_dir if split == 'train' else self.crops_val_dir
        label_dir = self.labels_train_dir if split == 'train' else self.labels_val_dir
        image_dir = self.images_train_dir if split == 'train' else self.images_val_dir

        sample_id = f'{image_stamp_ns}_{self.saved_count:07d}'

        x1, y1, x2, y2 = bbox
        ex1, ey1, ex2, ey2 = self.expand_bbox(x1, y1, x2, y2, width, height)
        crop = rgb[ey1:ey2, ex1:ex2]
        if crop.size == 0:
            self.skipped_count += 1
            return

        crop_path = os.path.join(crop_dir, f'{sample_id}.jpg')
        label_path = os.path.join(label_dir, f'{sample_id}.txt')
        image_path = os.path.join(image_dir, f'{sample_id}.jpg') if self.save_full_image else ''

        ok = cv2.imwrite(crop_path, crop, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            self.skipped_count += 1
            return

        with open(label_path, 'w', encoding='utf-8') as f:
            f.write(
                f'{yaw_cam:.8f} {sin_yaw_cam:.8f} {cos_yaw_cam:.8f} {yaw_world:.8f} {yaw_rel_world:.8f}\n'
            )

        if self.save_full_image:
            cv2.imwrite(image_path, rgb, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])

        if self.debug_labeled_images:
            debug_img = rgb.copy()
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.rectangle(debug_img, (ex1, ey1), (ex2, ey2), (255, 255, 0), 2)
            cv2.putText(
                debug_img,
                f'yaw_cam={yaw_cam:.2f} rad',
                (x1, max(22, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            debug_dir = self.debug_train_dir if split == 'train' else self.debug_val_dir
            debug_path = os.path.join(debug_dir, f'{sample_id}.jpg')
            cv2.imwrite(debug_path, debug_img, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])

        crop_relpath = os.path.relpath(crop_path, self.output_dir)
        label_relpath = os.path.relpath(label_path, self.output_dir)
        image_relpath = os.path.relpath(image_path, self.output_dir) if self.save_full_image else ''

        self.append_metadata_row(
            sample_id=sample_id,
            split=split,
            stamp_ns=image_stamp_ns,
            crop_relpath=crop_relpath,
            label_relpath=label_relpath,
            image_relpath=image_relpath,
            bbox_px=(x1, y1, x2, y2),
            yaw_world=yaw_world,
            yaw_rel_world=yaw_rel_world,
            yaw_cam=yaw_cam,
            sin_yaw_cam=sin_yaw_cam,
            cos_yaw_cam=cos_yaw_cam,
        )

        self.saved_count += 1

        if self.saved_count % 50 == 0 or self.frame_count % 200 == 0:
            self.get_logger().info(
                'Saved=%d (skipped=%d, occluded=%d, depth_stale=%d, depth_invalid=%d, last_split=%s)'
                % (
                    self.saved_count,
                    self.skipped_count,
                    self.occluded_count,
                    self.depth_stale_count,
                    self.depth_invalid_count,
                    split,
                )
            )


def main() -> None:
    rclpy.init()
    node = CollectHeadingDatasetNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
