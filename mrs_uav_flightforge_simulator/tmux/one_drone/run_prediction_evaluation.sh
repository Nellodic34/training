#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

ROS_SETUP="${ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
LOCAL_SETUP="${LOCAL_SETUP:-$WORKSPACE_DIR/local_setup.bash}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EVAL_SCRIPT="$SCRIPT_DIR/dataset_tools/evaluate_prediction_node.py"
AUTO_OPEN_RESULTS="${AUTO_OPEN_RESULTS:-0}"

OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/debug/evaluation}"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$OUTPUT_DIR/$TIMESTAMP"
mkdir -p "$RUN_DIR"

JSON_PATH="$RUN_DIR/prediction_eval.json"
PLOT_PATH="$RUN_DIR/prediction_eval_plot.png"
XY_PLOT_PATH="$RUN_DIR/prediction_eval_xy.png"
REPORT_PATH="$RUN_DIR/prediction_eval_report.md"
CSV_PATH="$RUN_DIR/prediction_eval_samples.csv"

ln -sfn "$RUN_DIR" "$OUTPUT_DIR/latest"

echo "[Evaluator] output directory: $RUN_DIR"
echo "[Evaluator] stop with Ctrl+C to finalize plot/report"

set +u
source "$ROS_SETUP"
source "$LOCAL_SETUP"
set -u

"$PYTHON_BIN" "$EVAL_SCRIPT" --ros-args \
  -p gt_odom_topic:=/uav3/hw_api/ground_truth \
  -p proposed_path_topic:=/target/predicted_trajectory \
  -p output_dir:="$RUN_DIR" \
  -p output_json_path:="$JSON_PATH" \
  -p output_plot_path:="$PLOT_PATH" \
  -p output_xy_plot_path:="$XY_PLOT_PATH" \
  -p output_report_path:="$REPORT_PATH" \
  -p output_csv_path:="$CSV_PATH" \
  "$@"

echo ""
echo "[Evaluator] artifacts:"
echo "  - $JSON_PATH"
echo "  - $PLOT_PATH"
echo "  - $XY_PLOT_PATH"
echo "  - $REPORT_PATH"
echo "  - $CSV_PATH"

if [[ "$AUTO_OPEN_RESULTS" == "1" ]] && command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$PLOT_PATH" >/dev/null 2>&1 || true
  xdg-open "$XY_PLOT_PATH" >/dev/null 2>&1 || true
  xdg-open "$REPORT_PATH" >/dev/null 2>&1 || true
fi
