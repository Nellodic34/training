#!/usr/bin/env bash

set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

FLIGHTFORGE_DIR="${FLIGHTFORGE_DIR:-$HOME/Pliska_FlightForge}"
FLIGHTFORGE_CMD="${FLIGHTFORGE_CMD:-./mrs_flight_forge.sh}"

ROS_SETUP="${ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
LOCAL_SETUP="${LOCAL_SETUP:-$WORKSPACE_DIR/local_setup.bash}"
VENV_ACTIVATE="${VENV_ACTIVATE:-$WORKSPACE_DIR/.venv/bin/activate}"
PYTHON_BIN="${PYTHON_BIN:-$WORKSPACE_DIR/.venv/bin/python}"
RUNTIME_STACK_CONFIG="${RUNTIME_STACK_CONFIG:-$SCRIPT_DIR/config/runtime_stack.yaml}"
RUNTIME_STACK_GENERATOR="${RUNTIME_STACK_GENERATOR:-$SCRIPT_DIR/generate_runtime_stack.py}"
DETECTION_SCRIPT="${DETECTION_SCRIPT:-$SCRIPT_DIR/dataset_tools/test_yolov8_realtime_node.py}"
TRIANGULATION_SCRIPT="${TRIANGULATION_SCRIPT:-$SCRIPT_DIR/dataset_tools/test_yolov8_multiview_triangulation_node.py}"
RQT_PLOT_CMD="${RQT_PLOT_CMD:-ros2 run rqt_plot rqt_plot /target/position_error/vector/x /target/position_error/vector/y /target/position_error/vector/z}"

if ! command -v gnome-terminal >/dev/null 2>&1; then
  echo "Errore: gnome-terminal non trovato."
  echo "Installa gnome-terminal oppure avvia manualmente i comandi dal README."
  exit 1
fi

if [ ! -d "$FLIGHTFORGE_DIR" ]; then
  echo "Errore: directory FlightForge non trovata: $FLIGHTFORGE_DIR"
  exit 1
fi

if [ ! -x "$SCRIPT_DIR/start.sh" ]; then
  echo "Errore: start.sh non trovato/eseguibile in $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$ROS_SETUP" ]; then
  echo "Errore: ROS setup non trovato: $ROS_SETUP"
  exit 1
fi

if [ ! -f "$LOCAL_SETUP" ]; then
  echo "Errore: local_setup.bash non trovato: $LOCAL_SETUP"
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Errore: interprete Python non trovato/eseguibile: $PYTHON_BIN"
  exit 1
fi

if [ ! -f "$RUNTIME_STACK_CONFIG" ]; then
  echo "Errore: config runtime non trovata: $RUNTIME_STACK_CONFIG"
  exit 1
fi

if [ ! -f "$RUNTIME_STACK_GENERATOR" ]; then
  echo "Errore: generatore runtime non trovato: $RUNTIME_STACK_GENERATOR"
  exit 1
fi

if [ ! -f "$VENV_ACTIVATE" ]; then
  echo "Errore: venv activate non trovato: $VENV_ACTIVATE"
  exit 1
fi

if [ ! -f "$DETECTION_SCRIPT" ]; then
  echo "Errore: detection script non trovato: $DETECTION_SCRIPT"
  exit 1
fi

if [ ! -f "$TRIANGULATION_SCRIPT" ]; then
  echo "Errore: triangulation script non trovato: $TRIANGULATION_SCRIPT"
  exit 1
fi

RUNTIME_STACK_CONFIG_PATH="$RUNTIME_STACK_CONFIG" FLIGHTFORGE_DIR="$FLIGHTFORGE_DIR" FLIGHTFORGE_CMD="$FLIGHTFORGE_CMD" ROS_SETUP="$ROS_SETUP" LOCAL_SETUP="$LOCAL_SETUP" VENV_ACTIVATE="$VENV_ACTIVATE" PYTHON_BIN="$PYTHON_BIN" DETECTION_SCRIPT="$DETECTION_SCRIPT" TRIANGULATION_SCRIPT="$TRIANGULATION_SCRIPT" "$PYTHON_BIN" "$RUNTIME_STACK_GENERATOR"

RUNTIME_ENV_PATH="$SCRIPT_DIR/generated/runtime.env"
if [ ! -f "$RUNTIME_ENV_PATH" ]; then
  echo "Errore: runtime env non generato: $RUNTIME_ENV_PATH"
  exit 1
fi

# shellcheck disable=SC1090
source "$RUNTIME_ENV_PATH"

gnome-terminal --title="MRS one_drone start" -- bash -lc "cd '$SCRIPT_DIR' && export SESSION_YML_PATH='$GENERATED_SESSION_YML_PATH' && ./start.sh"

sleep 2

case "$AUTO_START_NODE" in
  triangulation)
    echo "Nodo multi-view triangulation aggiunto alla finestra tmux 'triangulation'."
    ;;
  detection)
    echo "Nodo single-view detection aggiunto alla finestra tmux 'detection'."
    ;;
  none)
    echo "Finestra tmux 'perception_ready' aggiunta con l'ambiente pronto per i nodi detection e triangulation."
    ;;
  *)
    echo "Errore: AUTO_START_NODE non valido: $AUTO_START_NODE"
    exit 1
    ;;
esac

if [ "$OPEN_ERROR_PLOT" = "true" ]; then
  sleep "$PLOT_DELAY_SEC"

  gnome-terminal --title="Target error plot" -- bash -lc "cd '$WORKSPACE_DIR' && source '$ROS_SETUP' && source '$LOCAL_SETUP' && echo 'Apro rqt_plot sull errore di posizione del target...' && $RQT_PLOT_CMD"
fi

echo "Launcher completato. drone_count=$DRONE_COUNT, auto_start_node=$AUTO_START_NODE, open_error_plot=$OPEN_ERROR_PLOT, plot_delay_sec=$PLOT_DELAY_SEC, observer1=$OBSERVER1_NAME, observer2=$OBSERVER2_NAME, target=$TARGET_NAME"