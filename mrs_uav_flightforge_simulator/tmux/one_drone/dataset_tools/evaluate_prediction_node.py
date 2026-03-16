#!/usr/bin/env python3

import argparse
import csv
import json
import math
import traceback
from dataclasses import dataclass
from pathlib import Path as FsPath
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import rclpy
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node


def stamp_to_ns(stamp) -> int:
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def vec3_from_pose(pose_msg) -> np.ndarray:
    return np.array([pose_msg.position.x, pose_msg.position.y, pose_msg.position.z], dtype=np.float64)


@dataclass
class PendingPrediction:
    source: str
    created_ns: int
    pose_stamps_ns: List[int]
    positions: List[np.ndarray]


@dataclass
class EvaluatedPrediction:
    source: str
    created_ns: int
    pose_stamps_ns: List[int]
    predicted_positions: List[np.ndarray]
    gt_positions: List[np.ndarray]
    point_errors_m: List[float]
    velocity_errors_m: List[float]
    ade_m: float
    fde_m: float
    max_error_m: float
    position_rmse_m: float
    velocity_rmse_m: float


class PredictionEvaluatorNode(Node):
    def __init__(self) -> None:
        super().__init__('prediction_evaluator_node')

        default_output_dir = FsPath(__file__).resolve().parents[1] / 'debug' / 'evaluation'

        self.declare_parameter('gt_odom_topic', '/uav3/hw_api/ground_truth')
        self.declare_parameter('proposed_path_topic', '/target/predicted_trajectory')
        self.declare_parameter('baseline_path_topic', '')
        self.declare_parameter('stamp_tolerance_sec', 0.08)
        self.declare_parameter('max_pending_age_sec', 6.0)
        self.declare_parameter('report_every_n_paths', 25)
        self.declare_parameter('output_dir', str(default_output_dir))
        self.declare_parameter('output_json_path', '')
        self.declare_parameter('output_plot_path', '')
        self.declare_parameter('output_xy_plot_path', '')
        self.declare_parameter('output_report_path', '')
        self.declare_parameter('output_csv_path', '')

        self.declare_parameter('enable_known_trajectory_model', True)
        self.declare_parameter('model_initial_offset_x', 3.0)
        self.declare_parameter('model_initial_offset_z', 1.0)
        self.declare_parameter('model_pre_circle_climb_z', 0.5)
        self.declare_parameter('model_circle_radius', 4.0)
        self.declare_parameter('model_transition_speed', 0.6)
        self.declare_parameter('model_speed', 1.0)
        self.declare_parameter('plot_observer_markers', True)
        self.declare_parameter('observer1_odom_topic', '/uav1/hw_api/ground_truth')
        self.declare_parameter('observer2_odom_topic', '/uav2/hw_api/ground_truth')

        self.gt_odom_topic = str(self.get_parameter('gt_odom_topic').value)
        self.proposed_path_topic = str(self.get_parameter('proposed_path_topic').value)
        self.baseline_path_topic = str(self.get_parameter('baseline_path_topic').value)
        self.stamp_tolerance_ns = int(float(self.get_parameter('stamp_tolerance_sec').value) * 1e9)
        self.max_pending_age_ns = int(float(self.get_parameter('max_pending_age_sec').value) * 1e9)
        self.report_every_n_paths = max(1, int(self.get_parameter('report_every_n_paths').value))

        self.enable_known_trajectory_model = bool(self.get_parameter('enable_known_trajectory_model').value)
        self.model_initial_offset_x = float(self.get_parameter('model_initial_offset_x').value)
        self.model_initial_offset_z = float(self.get_parameter('model_initial_offset_z').value)
        self.model_pre_circle_climb_z = float(self.get_parameter('model_pre_circle_climb_z').value)
        self.model_circle_radius = max(0.1, float(self.get_parameter('model_circle_radius').value))
        self.model_transition_speed = max(0.05, float(self.get_parameter('model_transition_speed').value))
        self.model_speed = max(0.05, float(self.get_parameter('model_speed').value))
        self.plot_observer_markers = bool(self.get_parameter('plot_observer_markers').value)
        self.observer1_odom_topic = str(self.get_parameter('observer1_odom_topic').value)
        self.observer2_odom_topic = str(self.get_parameter('observer2_odom_topic').value)

        output_dir_value = str(self.get_parameter('output_dir').value).strip()
        self.output_dir = FsPath(output_dir_value) if output_dir_value else default_output_dir

        output_json_value = str(self.get_parameter('output_json_path').value).strip()
        if output_json_value:
            self.output_json_path = output_json_value
        else:
            self.output_json_path = str(self.output_dir / 'prediction_eval.json')

        json_path = FsPath(self.output_json_path)
        json_stem = json_path.with_suffix('') if json_path.suffix else FsPath(f'{self.output_json_path}_summary')
        self.output_plot_path = str(self.get_parameter('output_plot_path').value) or f'{json_stem}_plot.png'
        self.output_xy_plot_path = str(self.get_parameter('output_xy_plot_path').value) or f'{json_stem}_xy.png'
        self.output_report_path = str(self.get_parameter('output_report_path').value) or f'{json_stem}_report.md'
        self.output_csv_path = str(self.get_parameter('output_csv_path').value) or f'{json_stem}_samples.csv'

        self.gt_history: Dict[int, np.ndarray] = {}
        self.pending: List[PendingPrediction] = []
        self.evaluated_predictions: Dict[str, List[EvaluatedPrediction]] = {'proposed': [], 'baseline': []}
        self.evaluated_model_predictions: Dict[str, List[EvaluatedPrediction]] = {'proposed': [], 'baseline': []}
        self.finalized = False

        self.metrics = {
            'proposed': {
                'count': 0,
                'ade_sum': 0.0,
                'fde_sum': 0.0,
                'max_error_sum': 0.0,
                'pos_sq_error_sum': 0.0,
                'pos_point_count': 0,
                'vel_sq_error_sum': 0.0,
                'vel_point_count': 0,
            },
            'baseline': {
                'count': 0,
                'ade_sum': 0.0,
                'fde_sum': 0.0,
                'max_error_sum': 0.0,
                'pos_sq_error_sum': 0.0,
                'pos_point_count': 0,
                'vel_sq_error_sum': 0.0,
                'vel_point_count': 0,
            },
        }
        self.model_metrics = {
            'proposed': {
                'count': 0,
                'ade_sum': 0.0,
                'fde_sum': 0.0,
                'max_error_sum': 0.0,
                'pos_sq_error_sum': 0.0,
                'pos_point_count': 0,
                'vel_sq_error_sum': 0.0,
                'vel_point_count': 0,
            },
            'baseline': {
                'count': 0,
                'ade_sum': 0.0,
                'fde_sum': 0.0,
                'max_error_sum': 0.0,
                'pos_sq_error_sum': 0.0,
                'pos_point_count': 0,
                'vel_sq_error_sum': 0.0,
                'vel_point_count': 0,
            },
        }

        self.model_t0_ns: Optional[int] = None
        self.model_initial_position: Optional[np.ndarray] = None
        self.model_frame_id: str = ''
        self.gt_velocity_history: Dict[int, np.ndarray] = {}
        self.observer_positions: Dict[str, Optional[np.ndarray]] = {'observer1': None, 'observer2': None}
        self.gt_model_error_sum: float = 0.0
        self.gt_model_error_count: int = 0
        self.gt_model_error_max: float = 0.0

        self.create_subscription(Odometry, self.gt_odom_topic, self.gt_callback, 100)
        self.create_subscription(Path, self.proposed_path_topic, self.proposed_path_callback, 20)
        if self.baseline_path_topic.strip():
            self.create_subscription(Path, self.baseline_path_topic, self.baseline_path_callback, 20)
        if self.plot_observer_markers:
            if self.observer1_odom_topic.strip():
                self.create_subscription(
                    Odometry,
                    self.observer1_odom_topic,
                    lambda msg: self.observer_callback('observer1', msg),
                    20,
                )
            if self.observer2_odom_topic.strip():
                self.create_subscription(
                    Odometry,
                    self.observer2_odom_topic,
                    lambda msg: self.observer_callback('observer2', msg),
                    20,
                )

        self.create_timer(1.0, self.periodic_report)

        self.get_logger().info(f'GT topic: {self.gt_odom_topic}')
        self.get_logger().info(f'Proposed path topic: {self.proposed_path_topic}')
        if self.baseline_path_topic.strip():
            self.get_logger().info(f'Baseline path topic: {self.baseline_path_topic}')
        self.get_logger().info(f'Output directory: {self.output_dir}')
        self.get_logger().info(f'Known trajectory model enabled: {self.enable_known_trajectory_model}')
        if self.plot_observer_markers:
            self.get_logger().info(f'Observer marker topics: {self.observer1_odom_topic}, {self.observer2_odom_topic}')
        self.get_logger().info(f'Saving summary JSON to: {self.output_json_path}')
        self.get_logger().info(f'Saving final plot to: {self.output_plot_path}')
        self.get_logger().info(f'Saving XY comparison plot to: {self.output_xy_plot_path}')
        self.get_logger().info(f'Saving final report to: {self.output_report_path}')
        self.get_logger().info(f'Saving per-sample CSV to: {self.output_csv_path}')

    def observer_callback(self, role: str, msg: Odometry) -> None:
        self.observer_positions[role] = vec3_from_pose(msg.pose.pose)

    def known_trajectory_position(self, t_ns: int) -> Optional[np.ndarray]:
        if not self.enable_known_trajectory_model:
            return None
        if self.model_t0_ns is None or self.model_initial_position is None:
            return None

        p0 = self.model_initial_position
        p1 = np.array(
            [
                p0[0] + self.model_initial_offset_x,
                p0[1],
                p0[2] + self.model_initial_offset_z,
            ],
            dtype=np.float64,
        )
        p2 = np.array([p1[0], p1[1], p1[2] + self.model_pre_circle_climb_z], dtype=np.float64)

        d1 = float(np.linalg.norm(p1 - p0))
        d2 = float(abs(p2[2] - p1[2]))
        dt1 = d1 / self.model_transition_speed if d1 > 1e-6 else 0.0
        dt2 = d2 / self.model_transition_speed if d2 > 1e-6 else 0.0

        tau = max(0.0, (t_ns - self.model_t0_ns) / 1e9)

        if tau <= dt1 and dt1 > 0.0:
            ratio = tau / dt1
            return p0 + ratio * (p1 - p0)

        if tau <= dt1 + dt2 and dt2 > 0.0:
            ratio = (tau - dt1) / dt2
            return p1 + ratio * (p2 - p1)

        t_circle = max(0.0, tau - dt1 - dt2)
        radius = self.model_circle_radius
        angular_speed = self.model_speed / radius
        theta = angular_speed * t_circle
        center = np.array([p2[0] + radius, p2[1], p2[2]], dtype=np.float64)

        return np.array(
            [
                center[0] - radius * math.cos(theta),
                center[1] + radius * math.sin(theta),
                center[2],
            ],
            dtype=np.float64,
        )

    def circle_start_ns(self) -> Optional[int]:
        if self.model_t0_ns is None or self.model_initial_position is None:
            return None

        p0 = self.model_initial_position
        p1 = np.array(
            [
                p0[0] + self.model_initial_offset_x,
                p0[1],
                p0[2] + self.model_initial_offset_z,
            ],
            dtype=np.float64,
        )
        p2 = np.array([p1[0], p1[1], p1[2] + self.model_pre_circle_climb_z], dtype=np.float64)

        d1 = float(np.linalg.norm(p1 - p0))
        d2 = float(abs(p2[2] - p1[2]))
        dt1 = d1 / self.model_transition_speed if d1 > 1e-6 else 0.0
        dt2 = d2 / self.model_transition_speed if d2 > 1e-6 else 0.0
        return int(self.model_t0_ns + (dt1 + dt2) * 1e9)

    def nearest_gt_velocity(self, t_ns: int) -> Optional[np.ndarray]:
        if not self.gt_velocity_history:
            return None
        keys = list(self.gt_velocity_history.keys())
        nearest_k = min(keys, key=lambda k: abs(k - t_ns))
        if abs(nearest_k - t_ns) > self.stamp_tolerance_ns:
            return None
        return self.gt_velocity_history[nearest_k]

    def velocity_errors(
        self,
        stamps_ns: List[int],
        predicted_positions: List[np.ndarray],
    ) -> List[float]:
        if len(stamps_ns) < 2 or len(predicted_positions) < 2:
            return []

        errs: List[float] = []
        for idx in range(1, min(len(stamps_ns), len(predicted_positions))):
            dt = (stamps_ns[idx] - stamps_ns[idx - 1]) / 1e9
            if dt <= 1e-6:
                continue
            pred_v = (predicted_positions[idx] - predicted_positions[idx - 1]) / dt
            gt_v = self.nearest_gt_velocity(stamps_ns[idx])
            if gt_v is None:
                continue
            errs.append(float(np.linalg.norm(pred_v - gt_v)))
        return errs

    def gt_callback(self, msg: Odometry) -> None:
        t_ns = stamp_to_ns(msg.header.stamp)
        gt_position = vec3_from_pose(msg.pose.pose)
        gt_velocity = np.array(
            [
                msg.twist.twist.linear.x,
                msg.twist.twist.linear.y,
                msg.twist.twist.linear.z,
            ],
            dtype=np.float64,
        )
        self.gt_history[t_ns] = gt_position
        self.gt_velocity_history[t_ns] = gt_velocity

        if self.enable_known_trajectory_model and self.model_t0_ns is None:
            self.model_t0_ns = t_ns
            self.model_initial_position = gt_position.copy()
            self.model_frame_id = msg.header.frame_id

        if self.enable_known_trajectory_model:
            model_position = self.known_trajectory_position(t_ns)
            if model_position is not None:
                circle_start = self.circle_start_ns()
                if circle_start is not None and t_ns >= circle_start:
                    err = float(np.linalg.norm(gt_position - model_position))
                    self.gt_model_error_sum += err
                    self.gt_model_error_count += 1
                    self.gt_model_error_max = max(self.gt_model_error_max, err)

        # keep history bounded
        if len(self.gt_history) > 20000:
            keys = sorted(self.gt_history.keys())
            for k in keys[:5000]:
                self.gt_history.pop(k, None)
                self.gt_velocity_history.pop(k, None)

        self.try_evaluate_pending(current_gt_ns=t_ns)

    def proposed_path_callback(self, msg: Path) -> None:
        self.enqueue_prediction(msg, 'proposed')

    def baseline_path_callback(self, msg: Path) -> None:
        self.enqueue_prediction(msg, 'baseline')

    def enqueue_prediction(self, path_msg: Path, source: str) -> None:
        poses = path_msg.poses
        if len(poses) < 2:
            return

        stamps = [stamp_to_ns(p.header.stamp) for p in poses]
        positions = [vec3_from_pose(p.pose) for p in poses]

        self.pending.append(
            PendingPrediction(
                source=source,
                created_ns=stamp_to_ns(path_msg.header.stamp),
                pose_stamps_ns=stamps,
                positions=positions,
            )
        )

    def nearest_gt_position(self, t_ns: int) -> Optional[np.ndarray]:
        if not self.gt_history:
            return None

        keys = list(self.gt_history.keys())
        nearest_k = min(keys, key=lambda k: abs(k - t_ns))
        if abs(nearest_k - t_ns) > self.stamp_tolerance_ns:
            return None
        return self.gt_history[nearest_k]

    def evaluate_prediction(self, pred: PendingPrediction) -> Optional[EvaluatedPrediction]:
        circle_start = self.circle_start_ns()
        if circle_start is None:
            return None

        errs: List[float] = []
        gt_positions: List[np.ndarray] = []
        filtered_stamps: List[int] = []
        filtered_pred_positions: List[np.ndarray] = []

        for t_ns, p in zip(pred.pose_stamps_ns, pred.positions):
            if t_ns < circle_start:
                continue
            gt_p = self.nearest_gt_position(t_ns)
            if gt_p is None:
                return None
            filtered_stamps.append(t_ns)
            filtered_pred_positions.append(p.copy())
            gt_positions.append(gt_p.copy())
            errs.append(float(np.linalg.norm(p - gt_p)))

        if len(errs) < 2:
            return None

        vel_errs = self.velocity_errors(filtered_stamps, filtered_pred_positions)

        ade = float(np.mean(errs))
        fde = float(errs[-1])
        pos_rmse = float(np.sqrt(np.mean(np.square(np.asarray(errs, dtype=np.float64)))))
        vel_rmse = float(np.sqrt(np.mean(np.square(np.asarray(vel_errs, dtype=np.float64))))) if vel_errs else float('nan')
        return EvaluatedPrediction(
            source=pred.source,
            created_ns=pred.created_ns,
            pose_stamps_ns=filtered_stamps,
            predicted_positions=filtered_pred_positions,
            gt_positions=gt_positions,
            point_errors_m=errs,
            velocity_errors_m=vel_errs,
            ade_m=ade,
            fde_m=fde,
            max_error_m=float(max(errs)),
            position_rmse_m=pos_rmse,
            velocity_rmse_m=vel_rmse,
        )

    def evaluate_prediction_against_known(self, pred: PendingPrediction) -> Optional[EvaluatedPrediction]:
        if not self.enable_known_trajectory_model:
            return None

        circle_start = self.circle_start_ns()
        if circle_start is None:
            return None

        errs: List[float] = []
        model_positions: List[np.ndarray] = []
        filtered_stamps: List[int] = []
        filtered_pred_positions: List[np.ndarray] = []

        for t_ns, p in zip(pred.pose_stamps_ns, pred.positions):
            if t_ns < circle_start:
                continue
            ref_p = self.known_trajectory_position(t_ns)
            if ref_p is None:
                return None
            filtered_stamps.append(t_ns)
            filtered_pred_positions.append(p.copy())
            model_positions.append(ref_p.copy())
            errs.append(float(np.linalg.norm(p - ref_p)))

        if len(errs) < 2:
            return None

        vel_errs = self.velocity_errors(filtered_stamps, filtered_pred_positions)

        ade = float(np.mean(errs))
        fde = float(errs[-1])
        pos_rmse = float(np.sqrt(np.mean(np.square(np.asarray(errs, dtype=np.float64)))))
        vel_rmse = float(np.sqrt(np.mean(np.square(np.asarray(vel_errs, dtype=np.float64))))) if vel_errs else float('nan')
        return EvaluatedPrediction(
            source=pred.source,
            created_ns=pred.created_ns,
            pose_stamps_ns=filtered_stamps,
            predicted_positions=filtered_pred_positions,
            gt_positions=model_positions,
            point_errors_m=errs,
            velocity_errors_m=vel_errs,
            ade_m=ade,
            fde_m=fde,
            max_error_m=float(max(errs)),
            position_rmse_m=pos_rmse,
            velocity_rmse_m=vel_rmse,
        )

    def update_metrics(self, metric_store: Dict[str, Dict[str, float]], source: str, result: EvaluatedPrediction) -> None:
        m = metric_store[source]
        m['count'] += 1
        m['ade_sum'] += result.ade_m
        m['fde_sum'] += result.fde_m
        m['max_error_sum'] += result.max_error_m
        m['pos_sq_error_sum'] += float(np.sum(np.square(np.asarray(result.point_errors_m, dtype=np.float64))))
        m['pos_point_count'] += len(result.point_errors_m)
        if result.velocity_errors_m:
            m['vel_sq_error_sum'] += float(np.sum(np.square(np.asarray(result.velocity_errors_m, dtype=np.float64))))
            m['vel_point_count'] += len(result.velocity_errors_m)

    def try_evaluate_pending(self, current_gt_ns: int) -> None:
        keep: List[PendingPrediction] = []

        for pred in self.pending:
            # wait until enough future GT should be available
            if pred.pose_stamps_ns[-1] > current_gt_ns:
                keep.append(pred)
                continue

            result_gt = self.evaluate_prediction(pred)
            if result_gt is None:
                # if too old, drop
                if current_gt_ns - pred.created_ns <= self.max_pending_age_ns:
                    keep.append(pred)
                continue

            self.evaluated_predictions[pred.source].append(result_gt)
            self.update_metrics(self.metrics, pred.source, result_gt)

            if self.enable_known_trajectory_model:
                result_model = self.evaluate_prediction_against_known(pred)
                if result_model is not None:
                    self.evaluated_model_predictions[pred.source].append(result_model)
                    self.update_metrics(self.model_metrics, pred.source, result_model)

            if self.metrics[pred.source]['count'] % self.report_every_n_paths == 0:
                self.print_source_metrics(pred.source)

        self.pending = keep

    def source_summary(self, source: str, metric_store: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, float]:
        store = self.metrics if metric_store is None else metric_store
        m = store[source]
        cnt = m['count']
        if cnt == 0:
            return {
                'count': 0,
                'ade_m': float('nan'),
                'fde_m': float('nan'),
                'max_error_m': float('nan'),
                'position_rmse_m': float('nan'),
                'velocity_rmse_m': float('nan'),
            }

        pos_rmse = float('nan')
        if m['pos_point_count'] > 0:
            pos_rmse = float(math.sqrt(m['pos_sq_error_sum'] / m['pos_point_count']))

        vel_rmse = float('nan')
        if m['vel_point_count'] > 0:
            vel_rmse = float(math.sqrt(m['vel_sq_error_sum'] / m['vel_point_count']))

        return {
            'count': cnt,
            'ade_m': m['ade_sum'] / cnt,
            'fde_m': m['fde_sum'] / cnt,
            'max_error_m': m['max_error_sum'] / cnt,
            'position_rmse_m': pos_rmse,
            'velocity_rmse_m': vel_rmse,
        }

    def print_source_metrics(self, source: str) -> None:
        s_gt = self.source_summary(source, self.metrics)
        msg = (
            f"[{source}] GT count={s_gt['count']} ADE={s_gt['ade_m']:.3f}m "
            f"FDE={s_gt['fde_m']:.3f}m MAX={s_gt['max_error_m']:.3f}m "
            f"RMSE={s_gt['position_rmse_m']:.3f}m V_RMSE={s_gt['velocity_rmse_m']:.3f}m/s"
        )
        if self.enable_known_trajectory_model:
            s_model = self.source_summary(source, self.model_metrics)
            if s_model['count'] > 0:
                msg += (
                    f" | MODEL count={s_model['count']} ADE={s_model['ade_m']:.3f}m "
                    f"FDE={s_model['fde_m']:.3f}m MAX={s_model['max_error_m']:.3f}m "
                    f"RMSE={s_model['position_rmse_m']:.3f}m V_RMSE={s_model['velocity_rmse_m']:.3f}m/s"
                )
        self.get_logger().info(msg)

    def safe_div(self, numerator: float, denominator: float) -> float:
        if abs(denominator) < 1e-12:
            return float('nan')
        return numerator / denominator

    def build_summary_dict(self) -> Dict[str, object]:
        proposed = self.source_summary('proposed', self.metrics)
        baseline = self.source_summary('baseline', self.metrics)

        out: Dict[str, object] = {
            'proposed': proposed,
            'baseline': baseline,
            'improvement_percent': {},
            'known_trajectory_model': {},
            'ground_truth_vs_known_trajectory': {},
            'rviz_topics': {
                'predicted_trajectory': self.proposed_path_topic,
            },
            'artifacts': {
                'json': self.output_json_path,
                'plot': self.output_plot_path,
                'xy_plot': self.output_xy_plot_path,
                'report': self.output_report_path,
                'csv': self.output_csv_path,
            },
        }

        if proposed['count'] > 0 and baseline['count'] > 0:
            out['improvement_percent'] = {
                'ade': 100.0 * self.safe_div(baseline['ade_m'] - proposed['ade_m'], baseline['ade_m']),
                'fde': 100.0 * self.safe_div(baseline['fde_m'] - proposed['fde_m'], baseline['fde_m']),
                'max_error': 100.0 * self.safe_div(baseline['max_error_m'] - proposed['max_error_m'], baseline['max_error_m']),
            }

        if self.enable_known_trajectory_model:
            model_proposed = self.source_summary('proposed', self.model_metrics)
            model_baseline = self.source_summary('baseline', self.model_metrics)
            model_improvement = {}
            if model_proposed['count'] > 0 and model_baseline['count'] > 0:
                model_improvement = {
                    'ade': 100.0 * self.safe_div(model_baseline['ade_m'] - model_proposed['ade_m'], model_baseline['ade_m']),
                    'fde': 100.0 * self.safe_div(model_baseline['fde_m'] - model_proposed['fde_m'], model_baseline['fde_m']),
                    'max_error': 100.0 * self.safe_div(model_baseline['max_error_m'] - model_proposed['max_error_m'], model_baseline['max_error_m']),
                }
            out['known_trajectory_model'] = {
                'proposed': model_proposed,
                'baseline': model_baseline,
                'improvement_percent': model_improvement,
            }

            if self.gt_model_error_count > 0:
                out['ground_truth_vs_known_trajectory'] = {
                    'count': self.gt_model_error_count,
                    'mean_error_m': self.gt_model_error_sum / self.gt_model_error_count,
                    'max_error_m': self.gt_model_error_max,
                }

        return out

    def ensure_parent_dir(self, file_path: str) -> None:
        FsPath(file_path).parent.mkdir(parents=True, exist_ok=True)

    def format_metric(self, value: float) -> str:
        return 'n/a' if not math.isfinite(value) else f'{value:.3f}'

    def safe_log_info(self, message: str) -> None:
        try:
            self.get_logger().info(message)
        except Exception:
            print(message, flush=True)

    def write_json_summary(self) -> None:
        out = self.build_summary_dict()

        def sanitize_json(value):
            if isinstance(value, float):
                return value if math.isfinite(value) else None
            if isinstance(value, dict):
                return {k: sanitize_json(v) for k, v in value.items()}
            if isinstance(value, list):
                return [sanitize_json(v) for v in value]
            return value

        json_out = sanitize_json(out)
        try:
            self.ensure_parent_dir(self.output_json_path)
            with open(self.output_json_path, 'w', encoding='utf-8') as f:
                json.dump(json_out, f, indent=2)
        except Exception as exc:
            self.get_logger().warn(f'Failed writing summary JSON: {exc}')

    def write_csv_summary(self) -> None:
        try:
            self.ensure_parent_dir(self.output_csv_path)
            with open(self.output_csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'source',
                    'comparison',
                    'sample_index',
                    'created_time_sec',
                    'horizon_points',
                    'ade_m',
                    'fde_m',
                    'max_error_m',
                    'position_rmse_m',
                    'velocity_rmse_m',
                ])
                for source in ('proposed', 'baseline'):
                    for idx, sample in enumerate(self.evaluated_predictions[source], start=1):
                        writer.writerow([
                            source,
                            'ground_truth',
                            idx,
                            f'{sample.created_ns / 1e9:.3f}',
                            len(sample.point_errors_m),
                            f'{sample.ade_m:.6f}',
                            f'{sample.fde_m:.6f}',
                            f'{sample.max_error_m:.6f}',
                            f'{sample.position_rmse_m:.6f}',
                            '' if not math.isfinite(sample.velocity_rmse_m) else f'{sample.velocity_rmse_m:.6f}',
                        ])

                    for idx, sample in enumerate(self.evaluated_model_predictions[source], start=1):
                        writer.writerow([
                            source,
                            'known_trajectory_model',
                            idx,
                            f'{sample.created_ns / 1e9:.3f}',
                            len(sample.point_errors_m),
                            f'{sample.ade_m:.6f}',
                            f'{sample.fde_m:.6f}',
                            f'{sample.max_error_m:.6f}',
                            f'{sample.position_rmse_m:.6f}',
                            '' if not math.isfinite(sample.velocity_rmse_m) else f'{sample.velocity_rmse_m:.6f}',
                        ])
        except Exception as exc:
            self.get_logger().warn(f'Failed writing CSV summary: {exc}')

    def mean_error_profile(
        self,
        source: str,
        sample_store: Optional[Dict[str, List[EvaluatedPrediction]]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        store = self.evaluated_predictions if sample_store is None else sample_store
        samples = store[source]
        if not samples:
            return np.array([]), np.array([])

        max_len = max(len(sample.point_errors_m) for sample in samples)
        sums = np.zeros(max_len, dtype=np.float64)
        counts = np.zeros(max_len, dtype=np.int32)
        for sample in samples:
            errs = np.asarray(sample.point_errors_m, dtype=np.float64)
            sums[: len(errs)] += errs
            counts[: len(errs)] += 1

        valid = counts > 0
        steps = np.arange(max_len, dtype=np.int32)[valid]
        means = sums[valid] / counts[valid]
        return steps, means

    def add_xy_overlay(self, ax, source: str) -> None:
        ax.set_title(f'Circular phase: last {source} trajectory (XY)')
        ax.set_xlabel('x [m]')
        ax.set_ylabel('y [m]')
        ax.grid(True, alpha=0.25)

        samples = self.evaluated_predictions[source]
        if not samples:
            ax.text(0.5, 0.5, f'No {source} samples evaluated', ha='center', va='center', transform=ax.transAxes)
            return

        sample = samples[-1]
        if not sample.predicted_positions or not sample.gt_positions:
            ax.text(0.5, 0.5, f'No valid circular-phase points for {source}', ha='center', va='center', transform=ax.transAxes)
            return

        pred = np.vstack(sample.predicted_positions)
        gt = np.vstack(sample.gt_positions)
        ax.plot(pred[:, 0], pred[:, 1], 'o-', label=f'{source} predicted', linewidth=1.8, markersize=3)
        ax.plot(gt[:, 0], gt[:, 1], 's--', label='ground truth (circular phase)', linewidth=1.8, markersize=4, alpha=0.95)

        if self.enable_known_trajectory_model and self.evaluated_model_predictions[source]:
            model_sample = self.evaluated_model_predictions[source][-1]
            model = np.vstack(model_sample.gt_positions)
            ax.plot(model[:, 0], model[:, 1], 'x-.', label='known trajectory model', linewidth=1.2, markersize=4)

        ax.legend()

    def add_last_error_profile(self, ax, source: str) -> None:
        ax.set_title(f'Circular phase: last {source} position error over time')
        ax.set_xlabel('time from circular start [s]')
        ax.set_ylabel('error [m]')
        ax.grid(True, alpha=0.25)

        samples = self.evaluated_predictions[source]
        if not samples:
            ax.text(0.5, 0.5, f'No {source} samples evaluated', ha='center', va='center', transform=ax.transAxes)
            return

        sample = samples[-1]
        if not sample.pose_stamps_ns:
            ax.text(0.5, 0.5, f'No timestamps for {source} sample', ha='center', va='center', transform=ax.transAxes)
            return
        t0 = sample.pose_stamps_ns[0]
        times = (np.asarray(sample.pose_stamps_ns, dtype=np.float64) - float(t0)) / 1e9
        ax.plot(times, sample.point_errors_m, color='tab:red', linewidth=2.0)
        ax.axhline(sample.ade_m, color='tab:blue', linestyle='--', label=f'ADE={sample.ade_m:.3f}m')
        ax.axhline(sample.position_rmse_m, color='tab:purple', linestyle='-.', label=f'RMSE={sample.position_rmse_m:.3f}m')
        ax.axhline(sample.fde_m, color='tab:green', linestyle=':', label=f'FDE={sample.fde_m:.3f}m')
        ax.legend()

    def add_mean_error_profiles(self, ax) -> None:
        ax.set_title('Prediction error vs horizon (circular phase)')
        ax.set_xlabel('horizon step')
        ax.set_ylabel('mean error [m]')
        ax.grid(True, alpha=0.25)

        plotted = False
        for source, color in (('proposed', 'tab:blue'), ('baseline', 'tab:orange')):
            steps, means = self.mean_error_profile(source, self.evaluated_predictions)
            if steps.size > 0:
                ax.plot(steps, means, label=f'{source} vs GT', color=color, linewidth=2.0)
                plotted = True

            if self.enable_known_trajectory_model:
                steps_m, means_m = self.mean_error_profile(source, self.evaluated_model_predictions)
                if steps_m.size > 0:
                    ax.plot(steps_m, means_m, label=f'{source} vs model', color=color, linestyle='--', linewidth=1.6)
                    plotted = True

        if plotted:
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No evaluated predictions yet', ha='center', va='center', transform=ax.transAxes)

    def mean_velocity_error_profile(
        self,
        source: str,
        sample_store: Optional[Dict[str, List[EvaluatedPrediction]]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        store = self.evaluated_predictions if sample_store is None else sample_store
        samples = store[source]
        valid_samples = [s for s in samples if s.velocity_errors_m]
        if not valid_samples:
            return np.array([]), np.array([])

        max_len = max(len(sample.velocity_errors_m) for sample in valid_samples)
        sums = np.zeros(max_len, dtype=np.float64)
        counts = np.zeros(max_len, dtype=np.int32)
        for sample in valid_samples:
            errs = np.asarray(sample.velocity_errors_m, dtype=np.float64)
            sums[: len(errs)] += errs
            counts[: len(errs)] += 1

        valid = counts > 0
        steps = np.arange(max_len, dtype=np.int32)[valid]
        means = sums[valid] / counts[valid]
        return steps, means

    def add_mean_velocity_error_profiles(self, ax) -> None:
        ax.set_title('Velocity error vs horizon (circular phase)')
        ax.set_xlabel('horizon step')
        ax.set_ylabel('mean velocity error [m/s]')
        ax.grid(True, alpha=0.25)

        plotted = False
        for source, color in (('proposed', 'tab:blue'), ('baseline', 'tab:orange')):
            steps, means = self.mean_velocity_error_profile(source, self.evaluated_predictions)
            if steps.size > 0:
                ax.plot(steps, means, label=f'{source} vs GT', color=color, linewidth=2.0)
                plotted = True

            if self.enable_known_trajectory_model:
                steps_m, means_m = self.mean_velocity_error_profile(source, self.evaluated_model_predictions)
                if steps_m.size > 0:
                    ax.plot(steps_m, means_m, label=f'{source} vs model', color=color, linestyle='--', linewidth=1.6)
                    plotted = True

        if plotted:
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No velocity-error profiles available', ha='center', va='center', transform=ax.transAxes)

    def add_radius_over_time(self, ax, source: str) -> None:
        ax.set_title(f'Circular phase: radius consistency ({source})')
        ax.set_xlabel('time from circular start [s]')
        ax.set_ylabel('radius [m]')
        ax.grid(True, alpha=0.25)

        samples = self.evaluated_predictions[source]
        if not samples:
            ax.text(0.5, 0.5, f'No {source} samples evaluated', ha='center', va='center', transform=ax.transAxes)
            return

        sample = samples[-1]
        if not sample.pose_stamps_ns or not sample.predicted_positions or not sample.gt_positions:
            ax.text(0.5, 0.5, f'No valid circular-phase points for {source}', ha='center', va='center', transform=ax.transAxes)
            return

        if self.model_initial_position is None:
            ax.text(0.5, 0.5, 'Model center unavailable', ha='center', va='center', transform=ax.transAxes)
            return

        p0 = self.model_initial_position
        center_x = p0[0] + self.model_initial_offset_x + self.model_circle_radius
        center_y = p0[1]

        t0 = sample.pose_stamps_ns[0]
        times = (np.asarray(sample.pose_stamps_ns, dtype=np.float64) - float(t0)) / 1e9
        pred = np.vstack(sample.predicted_positions)
        gt = np.vstack(sample.gt_positions)

        pred_r = np.sqrt((pred[:, 0] - center_x) ** 2 + (pred[:, 1] - center_y) ** 2)
        gt_r = np.sqrt((gt[:, 0] - center_x) ** 2 + (gt[:, 1] - center_y) ** 2)

        ax.plot(times, gt_r, label='ground truth radius', color='tab:green', linewidth=1.8)
        ax.plot(times, pred_r, label=f'{source} predicted radius', color='tab:red', linewidth=1.8)
        ax.axhline(self.model_circle_radius, color='tab:gray', linestyle='--', label='known circle radius')
        ax.legend()

    def add_summary_panel(self, ax) -> None:
        ax.set_title('Final summary')
        ax.axis('off')

        summary = self.build_summary_dict()
        proposed = summary['proposed']
        baseline = summary['baseline']
        improvement = summary['improvement_percent']

        lines = [
            'Prediction vs ground truth',
            'source      count   ADE [m]   FDE [m]   MAX [m]   RMSE [m]   V_RMSE [m/s]',
            f"proposed    {proposed['count']:>5}   {self.format_metric(proposed['ade_m']):>7}   {self.format_metric(proposed['fde_m']):>7}   {self.format_metric(proposed['max_error_m']):>7}   {self.format_metric(proposed['position_rmse_m']):>8}   {self.format_metric(proposed['velocity_rmse_m']):>11}",
            f"baseline    {baseline['count']:>5}   {self.format_metric(baseline['ade_m']):>7}   {self.format_metric(baseline['fde_m']):>7}   {self.format_metric(baseline['max_error_m']):>7}   {self.format_metric(baseline['position_rmse_m']):>8}   {self.format_metric(baseline['velocity_rmse_m']):>11}",
        ]

        if improvement:
            lines.extend([
                f"GT improvement ADE: {self.format_metric(float(improvement['ade']))}%",
                f"GT improvement FDE: {self.format_metric(float(improvement['fde']))}%",
            ])

        known = summary.get('known_trajectory_model', {})
        if isinstance(known, dict) and known:
            kp = known.get('proposed', {})
            kb = known.get('baseline', {})
            lines.extend([
                '',
                'Prediction vs known model',
                'source      count   ADE [m]   FDE [m]   MAX [m]   RMSE [m]   V_RMSE [m/s]',
                f"proposed    {int(kp.get('count', 0)):>5}   {self.format_metric(float(kp.get('ade_m', float('nan')))):>7}   {self.format_metric(float(kp.get('fde_m', float('nan')))):>7}   {self.format_metric(float(kp.get('max_error_m', float('nan')))):>7}   {self.format_metric(float(kp.get('position_rmse_m', float('nan')))):>8}   {self.format_metric(float(kp.get('velocity_rmse_m', float('nan')))):>11}",
                f"baseline    {int(kb.get('count', 0)):>5}   {self.format_metric(float(kb.get('ade_m', float('nan')))):>7}   {self.format_metric(float(kb.get('fde_m', float('nan')))):>7}   {self.format_metric(float(kb.get('max_error_m', float('nan')))):>7}   {self.format_metric(float(kb.get('position_rmse_m', float('nan')))):>8}   {self.format_metric(float(kb.get('velocity_rmse_m', float('nan')))):>11}",
            ])

        gt_model = summary.get('ground_truth_vs_known_trajectory', {})
        if isinstance(gt_model, dict) and gt_model:
            lines.extend([
                '',
                f"GT vs model mean error: {self.format_metric(float(gt_model.get('mean_error_m', float('nan'))))} m",
                f"GT vs model max error : {self.format_metric(float(gt_model.get('max_error_m', float('nan'))))} m",
            ])

        ax.text(0.02, 0.98, '\n'.join(lines), ha='left', va='top', family='monospace', fontsize=9)

    def write_plot(self) -> None:
        try:
            self.ensure_parent_dir(self.output_plot_path)
            fig, axes = plt.subplots(2, 3, figsize=(18, 10))
            self.add_xy_overlay(axes[0, 0], 'proposed')
            self.add_last_error_profile(axes[0, 1], 'proposed')
            self.add_radius_over_time(axes[0, 2], 'proposed')
            self.add_mean_error_profiles(axes[1, 0])
            self.add_mean_velocity_error_profiles(axes[1, 1])
            self.add_summary_panel(axes[1, 2])
            fig.suptitle('Prediction quality report (circular phase only)', fontsize=14)
            fig.tight_layout()
            fig.savefig(self.output_plot_path, dpi=180, bbox_inches='tight')
            plt.close(fig)
        except Exception as exc:
            self.get_logger().warn(f'Failed writing plot: {exc}')
            self.get_logger().warn(traceback.format_exc())

    def add_known_circle(self, ax) -> bool:
        if self.model_initial_position is None:
            return False

        center_x = self.model_initial_position[0] + self.model_initial_offset_x + self.model_circle_radius
        center_y = self.model_initial_position[1]
        theta = np.linspace(0.0, 2.0 * np.pi, 360)
        x = center_x - self.model_circle_radius * np.cos(theta)
        y = center_y + self.model_circle_radius * np.sin(theta)
        ax.plot(x, y, color='tab:green', linestyle='--', linewidth=2.0, label='known circular trajectory')
        return True

    def add_prediction_cloud_xy(self, ax, source: str, color: str) -> None:
        samples = self.evaluated_predictions[source]
        if not samples:
            return

        for idx, sample in enumerate(samples):
            if not sample.predicted_positions:
                continue
            pred = np.vstack(sample.predicted_positions)
            label = f'{source} predictions' if idx == 0 else None
            ax.plot(pred[:, 0], pred[:, 1], color=color, alpha=0.14, linewidth=1.0, label=label)

        last = samples[-1]
        if last.predicted_positions:
            pred_last = np.vstack(last.predicted_positions)
            ax.plot(
                pred_last[:, 0],
                pred_last[:, 1],
                color=color,
                linewidth=2.2,
                label=f'{source} last prediction',
            )

    def add_observer_markers(self, ax) -> None:
        if not self.plot_observer_markers:
            return

        legend_added = False
        for role in ('observer1', 'observer2'):
            pos = self.observer_positions.get(role)
            if pos is None:
                continue
            label = 'observers pose' if not legend_added else None
            ax.scatter([pos[0]], [pos[1]], color='tab:green', marker='>', s=90, zorder=5, label=label)
            legend_added = True

    def write_xy_plot(self) -> None:
        try:
            self.ensure_parent_dir(self.output_xy_plot_path)
            fig, ax = plt.subplots(1, 1, figsize=(10, 8))

            source = 'proposed'
            ax.set_title('Circular XY comparison (proposed only)')
            ax.set_xlabel('x [m]')
            ax.set_ylabel('y [m]')
            ax.grid(True, alpha=0.25)
            circle_ok = self.add_known_circle(ax)
            self.add_prediction_cloud_xy(ax, source, 'tab:red')
            self.add_observer_markers(ax)
            if not circle_ok and not self.evaluated_predictions[source]:
                ax.text(0.5, 0.5, 'No circular-phase data available', ha='center', va='center', transform=ax.transAxes)
            ax.set_aspect('equal', adjustable='box')
            ax.legend(loc='best')

            fig.suptitle('Known circular trajectory vs predicted trajectories (proposed)', fontsize=14)
            fig.tight_layout()
            fig.savefig(self.output_xy_plot_path, dpi=180, bbox_inches='tight')
            plt.close(fig)
        except Exception as exc:
            self.get_logger().warn(f'Failed writing XY comparison plot: {exc}')
            self.get_logger().warn(traceback.format_exc())

    def build_worst_samples_table(
        self,
        source: str,
        sample_store: Optional[Dict[str, List[EvaluatedPrediction]]] = None,
        limit: int = 5,
    ) -> List[str]:
        rows = [
            '| rank | created_s | points | ADE [m] | RMSE [m] | FDE [m] | MAX [m] | V_RMSE [m/s] |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
        ]
        store = self.evaluated_predictions if sample_store is None else sample_store
        samples = sorted(store[source], key=lambda s: s.ade_m, reverse=True)[:limit]
        if not samples:
            rows.append('| - | - | - | - | - | - | - | - |')
            return rows

        for rank, sample in enumerate(samples, start=1):
            rows.append(
                f"| {rank} | {sample.created_ns / 1e9:.3f} | {len(sample.point_errors_m)} | {sample.ade_m:.3f} | {sample.position_rmse_m:.3f} | {sample.fde_m:.3f} | {sample.max_error_m:.3f} | {self.format_metric(sample.velocity_rmse_m)} |"
            )
        return rows

    def write_report(self) -> None:
        try:
            self.ensure_parent_dir(self.output_report_path)
            summary = self.build_summary_dict()
            proposed = summary['proposed']
            baseline = summary['baseline']
            improvement = summary['improvement_percent']

            lines = [
                '# Prediction evaluation report',
                '',
                '## Prediction vs ground truth',
                '',
                '| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |',
                '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
                f"| proposed | {proposed['count']} | {self.format_metric(float(proposed['ade_m']))} | {self.format_metric(float(proposed['position_rmse_m']))} | {self.format_metric(float(proposed['fde_m']))} | {self.format_metric(float(proposed['max_error_m']))} | {self.format_metric(float(proposed['velocity_rmse_m']))} |",
                f"| baseline | {baseline['count']} | {self.format_metric(float(baseline['ade_m']))} | {self.format_metric(float(baseline['position_rmse_m']))} | {self.format_metric(float(baseline['fde_m']))} | {self.format_metric(float(baseline['max_error_m']))} | {self.format_metric(float(baseline['velocity_rmse_m']))} |",
                '',
            ]

            if improvement:
                lines.extend([
                    '### Improvement vs baseline (ground truth)',
                    '',
                    '| metric | improvement [%] |',
                    '| --- | ---: |',
                    f"| ADE | {self.format_metric(float(improvement['ade']))} |",
                    f"| FDE | {self.format_metric(float(improvement['fde']))} |",
                    f"| MAX error | {self.format_metric(float(improvement['max_error']))} |",
                    '',
                ])

            known = summary.get('known_trajectory_model', {})
            if isinstance(known, dict) and known:
                kp = known.get('proposed', {})
                kb = known.get('baseline', {})
                kimpr = known.get('improvement_percent', {})
                lines.extend([
                    '## Prediction vs known trajectory model',
                    '',
                    '| source | count | ADE [m] | RMSE pos [m] | FDE [m] | MAX error [m] | RMSE vel [m/s] |',
                    '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
                    f"| proposed | {int(kp.get('count', 0))} | {self.format_metric(float(kp.get('ade_m', float('nan'))))} | {self.format_metric(float(kp.get('position_rmse_m', float('nan'))))} | {self.format_metric(float(kp.get('fde_m', float('nan'))))} | {self.format_metric(float(kp.get('max_error_m', float('nan'))))} | {self.format_metric(float(kp.get('velocity_rmse_m', float('nan'))))} |",
                    f"| baseline | {int(kb.get('count', 0))} | {self.format_metric(float(kb.get('ade_m', float('nan'))))} | {self.format_metric(float(kb.get('position_rmse_m', float('nan'))))} | {self.format_metric(float(kb.get('fde_m', float('nan'))))} | {self.format_metric(float(kb.get('max_error_m', float('nan'))))} | {self.format_metric(float(kb.get('velocity_rmse_m', float('nan'))))} |",
                    '',
                ])

                if isinstance(kimpr, dict) and kimpr:
                    lines.extend([
                        '### Improvement vs baseline (known model)',
                        '',
                        '| metric | improvement [%] |',
                        '| --- | ---: |',
                        f"| ADE | {self.format_metric(float(kimpr.get('ade', float('nan'))))} |",
                        f"| FDE | {self.format_metric(float(kimpr.get('fde', float('nan'))))} |",
                        f"| MAX error | {self.format_metric(float(kimpr.get('max_error', float('nan'))))} |",
                        '',
                    ])

            gt_model = summary.get('ground_truth_vs_known_trajectory', {})
            if isinstance(gt_model, dict) and gt_model:
                lines.extend([
                    '## Real trajectory consistency vs known model',
                    '',
                    '| count | mean error [m] | max error [m] |',
                    '| ---: | ---: | ---: |',
                    f"| {int(gt_model.get('count', 0))} | {self.format_metric(float(gt_model.get('mean_error_m', float('nan'))))} | {self.format_metric(float(gt_model.get('max_error_m', float('nan'))))} |",
                    '',
                ])

            lines.extend([
                '## Worst proposed predictions by ADE (vs GT)',
                '',
                *self.build_worst_samples_table('proposed', self.evaluated_predictions),
                '',
                '## Worst baseline predictions by ADE (vs GT)',
                '',
                *self.build_worst_samples_table('baseline', self.evaluated_predictions),
                '',
                '> Note: all metrics and plots are computed only on the circular phase of the trajectory.',
                '',
                '## RViz topics',
                '',
                f"- predicted trajectory: `{self.proposed_path_topic}`",
                '',
                '## Artifacts',
                '',
                f'- JSON summary: `{self.output_json_path}`',
                f'- Plot PNG: `{self.output_plot_path}`',
                f'- XY comparison PNG: `{self.output_xy_plot_path}`',
                f'- Per-sample CSV: `{self.output_csv_path}`',
            ])

            with open(self.output_report_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
        except Exception as exc:
            self.get_logger().warn(f'Failed writing Markdown report: {exc}')

    def finalize_report(self) -> None:
        if self.finalized:
            return
        self.finalized = True

        self.write_json_summary()
        self.write_csv_summary()
        self.write_plot()
        self.write_xy_plot()
        self.write_report()

        self.safe_log_info('Final evaluation artifacts saved:')
        self.safe_log_info(f'  JSON: {self.output_json_path}')
        self.safe_log_info(f'  PNG : {self.output_plot_path}')
        self.safe_log_info(f'  XY  : {self.output_xy_plot_path}')
        self.safe_log_info(f'  CSV : {self.output_csv_path}')
        self.safe_log_info(f'  MD  : {self.output_report_path}')

    def periodic_report(self) -> None:
        self.write_json_summary()


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.parse_known_args()

    rclpy.init()
    node = PredictionEvaluatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.finalize_report()
        try:
            node.destroy_node()
        except Exception:
            pass

        try:
            rclpy.try_shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
