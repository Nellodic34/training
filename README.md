# UAV Multi-View Detection & Triangulation

Real-time multi-drone detection and 3D triangulation using YOLOv8 in a simulated environment (FlightForge + MRS UAV System + ROS 2 Jazzy).

Two observer UAVs detect a target UAV independently using a shared YOLOv8 model.
Their 2D detections are back-projected into 3D bearing rays, then geometrically triangulated to estimate the target's position in the world frame.
The estimate is compared with simulator ground truth in real time.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [System Architecture](#system-architecture)
3. [Repository Structure](#repository-structure)
4. [Installation](#installation)
5. [YOLO Weights](#yolo-weights)
6. [Configuration](#configuration)
7. [Running](#running)
8. [Available ROS 2 Topics](#available-ros-2-topics)
9. [Monitoring & Plotting](#monitoring--plotting)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

The following must be installed **before** cloning this repository:

| Dependency | Version | Installation guide |
|---|---|---|
| **Ubuntu** | 24.04 LTS (Noble) | — |
| **ROS 2** | Jazzy Jalisco | [docs.ros.org/en/jazzy](https://docs.ros.org/en/jazzy/Installation.html) |
| **MRS UAV System** | Latest (Jazzy branch) | [github.com/ctu-mrs/mrs_uav_system](https://github.com/ctu-mrs/mrs_uav_system/tree/ros2) |
| **FlightForge simulator** | v0.11+ | Binary from [CTU-MRS](https://nasmrs.fel.cvut.cz/index.php/s/MnGARsSwnpeVy5z) |
| **Python** | 3.12 (ships with Ubuntu 24.04) | `sudo apt install python3.12 python3.12-venv` |
| **tmuxinator** | any | `sudo apt install tmuxinator` |
| **gnome-terminal** | any | `sudo apt install gnome-terminal` (for the one-command launcher) |

### FlightForge location

By default the launcher expects FlightForge at:

```
~/Pliska_FlightForge/mrs_flight_forge.sh
```

If your FlightForge is installed elsewhere, set the environment variable before launching:

```bash
export FLIGHTFORGE_DIR=/path/to/your/FlightForge_Linux_vX_Y_Z/Linux
```

---

## System Architecture

```
┌─────────────┐     ┌─────────────┐
│   UAV 1     │     │   UAV 2     │
│  (observer) │     │  (observer) │
│             │     │             │
│ rgb/image   │     │ rgb/image   │
│ camera_info │     │ camera_info │
│ ground_truth│     │ ground_truth│
└──────┬──────┘     └──────┬──────┘
       │                   │
       └─────────┬─────────┘
                 │
    ┌────────────▼────────────┐
    │  Multiview Triangulation │
    │         Node             │
    │                          │
    │  • YOLOv8 detection ×2   │
    │  • bearing ray extraction│
    │  • midpoint triangulation│
    │  • velocity estimation   │
    │  • GT error computation  │
    └────────────┬─────────────┘
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
  /uav1/     /target/   /target/
  detection  position   position
  /uav2/     _estimate  _error
  detection
```

---

## Repository Structure

```
training/
├── README.md                          ← this file
├── requirements.txt                   ← Python dependencies
├── .gitignore
└── mrs_uav_flightforge_simulator/
    ├── local_setup.bash               ← ROS 2 workspace overlay setup
    ├── config/                        ← installed package configs
    ├── launch/                        ← ROS 2 launch files
    └── tmux/
        └── one_drone/
            ├── start.sh               ← starts tmux simulation session
            ├── kill.sh                 ← kills the session
            ├── launch_realtime_stack.sh ← one-command launcher (recommended)
            ├── generate_runtime_stack.py ← generates runtime YAML from base configs
            ├── config/
            │   ├── simulator.yaml      ← world, sensors, spawn positions
            │   ├── network_config.yaml ← UAV network
            │   ├── world_config.yaml   ← GPS origin for the world (critical!)
            │   ├── runtime_stack.yaml  ← what to auto-launch (node, drone count)
            │   └── generated/          ← auto-generated at launch (gitignored)
            ├── generated/              ← auto-generated session.yml (gitignored)
            └── dataset_tools/
                ├── test_yolov8_realtime_node.py              ← single-view detection
                ├── test_yolov8_multiview_triangulation_node.py ← multi-view triangulation
                ├── collect_yolo_dataset_node.py               ← dataset collection
                ├── README_dataset_collection.md               ← dataset collection guide
```

---

## Installation

### 1. Clone the repository

```bash
cd ~/git
git clone https://github.com/NelloDic34/training.git
cd training
```

### 2. Create the Python virtual environment

The `.venv` **must** use the system Python 3.12 (same as ROS 2 Jazzy):

```bash
cd mrs_uav_flightforge_simulator
python3.12 -m venv .venv --system-site-packages
source .venv/bin/activate
```

> **Important:** the `--system-site-packages` flag gives the venv access to ROS 2 Python packages (`rclpy`, `cv_bridge`, `sensor_msgs`, etc.) that are installed system-wide. Without it, `import rclpy` will fail.

> **Warning:** do **not** use a Conda environment. Conda ships its own `libpython3.x` which is ABI-incompatible with the ROS 2 `rclpy` bindings compiled against the system Python.

### 3. Install Python dependencies

```bash
pip install -r ../requirements.txt
```

### 4. Verify the installation

```bash
python -c "import rclpy, cv_bridge, ultralytics, numpy, cv2; print('All imports OK')"
```

Expected output: `All imports OK`

---

## YOLO Weights

The detection nodes need a trained YOLOv8 weights file (`.pt`).
Weights are **not included** in this repository because they exceed GitHub's 100 MB file size limit.

### Default path expected by the nodes

```
~/datasets/uav_detector/20260227_174226/runs/detect/exp1/run1_debug2/weights/best.pt
```

### Setup

**Option A** — Place weights at the default path:

```bash
mkdir -p ~/datasets/uav_detector/20260227_174226/runs/detect/exp1/run1_debug2/weights/
cp /path/to/your/best.pt ~/datasets/uav_detector/20260227_174226/runs/detect/exp1/run1_debug2/weights/
```

**Option B** — Override the path at runtime via ROS parameter:

```bash
python test_yolov8_multiview_triangulation_node.py \
  --ros-args -p model_path:=/your/custom/path/best.pt
```

### Training your own weights

See `dataset_tools/README_dataset_collection.md` for how to collect a YOLO training dataset using the simulator, then train with:

```bash
yolo detect train data=~/datasets/uav_detector/<timestamp>/dataset.yaml model=yolov8n.pt epochs=100 imgsz=640
```

---

## Configuration

All runtime behavior is controlled from a single YAML file:

### `tmux/one_drone/config/runtime_stack.yaml`

```yaml
launcher:
  auto_start_node: triangulation  # none | detection | triangulation
  open_error_plot: true            # auto-open rqt_plot with position error
  plot_delay_sec: 10               # seconds to wait before opening plot

simulation:
  drone_count: 3                   # 1, 2, or 3
```

| Option | Values | Description |
|---|---|---|
| `auto_start_node` | `none` | Only start simulator + MRS stack, no detection |
| | `detection` | Single-view YOLOv8 detection on `uav1` camera |
| | `triangulation` | Multi-view detection + 3D triangulation using `uav1` + `uav2` |
| `open_error_plot` | `true`/`false` | Auto-open `rqt_plot` showing triangulation error vs GT |
| `plot_delay_sec` | integer | Delay before opening plot (let the system stabilize) |
| `drone_count` | `1` | Single drone only |
| | `2` | Two drones: `uav1` (observer) + `uav2` (uses `uav3` spawn position) |
| | `3` | Three drones: `uav1` + `uav2` (observers) + `uav3` (target) |

### Simulator settings — `tmux/one_drone/config/simulator.yaml`

Key parameters:

- `world_name`: FlightForge world (e.g., `temesvar`, `valley`, `forest`, `warehouse`)
- `graphics_settings`: `low`, `medium`, `high`, `epic`, `cinematic`
- RGB camera: `rate`, `width`, `height`
- Sensor toggles: lidar, stereo, depth, segmentation
- UAV spawn positions: `uav1.spawn`, `uav2.spawn`, `uav3.spawn`

### World origin — `tmux/one_drone/config/world_config.yaml`

This file defines the GPS origin that the MRS estimation manager uses. **It must match the FlightForge world**.

| FlightForge world | `origin_x` (latitude) | `origin_y` (longitude) |
|---|---|---|
| `temesvar` | `47.397788` | `8.545594` |
| `forest` / `valley` | `48.316131` | `11.935897` |

> **Critical:** if the GPS origin is wrong, the estimation manager will report positions hundreds of km from the origin. Drones will crash immediately on any command (remote controller or goto). The estimation manager log will show: `"Not expected to fly further than 10 km. This is most likely a bug."`

---

## Running

### One-command launch (recommended)

```bash
cd ~/git/training/mrs_uav_flightforge_simulator
./tmux/one_drone/launch_realtime_stack.sh
```

This will:
1. Open FlightForge simulator (or connect to a running instance)
2. Generate runtime configs from `runtime_stack.yaml`
3. Start the tmux session with all UAVs
4. (If configured) start the detection or triangulation node in a separate terminal
5. (If configured) open `rqt_plot` after the configured delay

### Manual launch (step by step)

**Terminal 1 — FlightForge:**

```bash
cd ~/Pliska_FlightForge
./mrs_flight_forge.sh
```

**Terminal 2 — MRS simulation session:**

```bash
cd ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone
./start.sh
```

Wait until all UAVs show `FLYING_NORMALLY` in their status windows.

**Terminal 3 — Detection / triangulation node:**

```bash
source /opt/ros/jazzy/setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/local_setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/.venv/bin/activate
cd ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools
```

For **single-view detection** only:

```bash
python test_yolov8_realtime_node.py
```

For **multi-view triangulation**:

```bash
python test_yolov8_multiview_triangulation_node.py
```

### Stopping everything

```bash
cd ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone
./kill.sh
```

---

## Available ROS 2 Topics

### Published by the triangulation node

| Topic | Type | Description |
|---|---|---|
| `/uav1/detection` | `sensor_msgs/Image` | UAV1 camera with bounding boxes drawn |
| `/uav2/detection` | `sensor_msgs/Image` | UAV2 camera with bounding boxes drawn |
| `/target/pose_estimate` | `geometry_msgs/PoseStamped` | Triangulated 3D target position |
| `/target/odometry_estimate` | `nav_msgs/Odometry` | Position + estimated velocity |
| `/target/position_estimate` | `geometry_msgs/Vector3Stamped` | Position as (x, y, z) |
| `/target/position_error` | `geometry_msgs/Vector3Stamped` | Error vs ground truth (dx, dy, dz) |

### Published by the single-view detection node

| Topic | Type | Description |
|---|---|---|
| `/test_img` | `sensor_msgs/Image` | Input image with bounding boxes overlaid |

### Input topics consumed

| Topic | Source |
|---|---|
| `/uav1/rgb/image_raw` | UAV1 RGB camera |
| `/uav2/rgb/image_raw` | UAV2 RGB camera |
| `/uav1/rgb/camera_info` | UAV1 camera intrinsics |
| `/uav2/rgb/camera_info` | UAV2 camera intrinsics |
| `/uav1/hw_api/ground_truth` | UAV1 odometry (pose + orientation) |
| `/uav2/hw_api/ground_truth` | UAV2 odometry |
| `/uav3/hw_api/ground_truth` | Target UAV ground truth (for error computation) |

---

## Monitoring & Plotting

### View detection images

```bash
ros2 run rqt_image_view rqt_image_view /uav1/detection
ros2 run rqt_image_view rqt_image_view /uav2/detection
```

### Echo topics in terminal

```bash
# Position estimate
ros2 topic echo /target/position_estimate

# Position error vs ground truth
ros2 topic echo /target/position_error
```

### Real-time plots with rqt_plot

```bash
# Triangulation error
ros2 run rqt_plot rqt_plot \
  /target/position_error/vector/x \
  /target/position_error/vector/y \
  /target/position_error/vector/z

# Position estimate
ros2 run rqt_plot rqt_plot \
  /target/position_estimate/vector/x \
  /target/position_estimate/vector/y \
  /target/position_estimate/vector/z
```

> **Note:** always `source /opt/ros/jazzy/setup.bash` and `source local_setup.bash` before using `ros2` commands.

---

## Troubleshooting

### Drones crash immediately on any command

**Cause:** wrong GPS origin in `world_config.yaml`. The estimation manager sees positions hundreds of km from origin and the controller generates invalid commands.

**Fix:** set `origin_x` and `origin_y` to match the FlightForge world. For `temesvar`: `47.397788`, `8.545594`. See the [World origin](#world-origin--tmxone_droneconfigworld_configyaml) section.

**Symptom in logs:** `"Not expected to fly further than 10 km. This is most likely a bug."`

### `ModuleNotFoundError: rclpy._rclpy_pybind11`

**Cause:** wrong Python version or `.venv` created without `--system-site-packages`.

**Fix:** recreate the venv:

```bash
rm -rf .venv
python3.12 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r ../requirements.txt
```

### `ModuleNotFoundError: ultralytics`

**Cause:** `.venv` not activated or dependencies not installed.

**Fix:** `source .venv/bin/activate && pip install -r ../requirements.txt`

### `FileNotFoundError: Model not found: .../best.pt`

**Cause:** YOLO weights file not present at the expected path.

**Fix:** see [YOLO Weights](#yolo-weights) section.

### Triangulation node stops publishing

**Cause:** system overload, frames arriving too slowly, or both drones not in view of target.

**Fix:** lower processing rate or YOLO image size:

```bash
python test_yolov8_multiview_triangulation_node.py \
  --ros-args -p processing_rate_hz:=2.0 -p imgsz:=512
```

### Simulation is very slow (RTF < 1.0)

**Fix:** in `simulator.yaml`:
- Set `graphics_settings: "low"`
- Disable unused sensors (lidar, stereo, segmentation)
- Lower RGB resolution and frame rate

### `rqt_plot` or `rqt_image_view` not found

**Fix:**

```bash
source /opt/ros/jazzy/setup.bash
sudo apt install ros-jazzy-rqt-plot ros-jazzy-rqt-image-view
```

---

## Additional Docs

- [Dataset collection guide](mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/README_dataset_collection.md) — how to collect a YOLO training dataset from the simulator
- [Realtime detection (legacy)](mrs_uav_flightforge_simulator/tmux/one_drone/README_realtime_detection_OLD.md) — older Italian-language notes on the launcher

---

## References

- [MRS UAV System](https://github.com/ctu-mrs/mrs_uav_system/tree/ros2)
- [FlightForge Simulator](https://github.com/ctu-mrs/mrs_uav_flightforge_simulator/tree/ros2)
- [Ultralytics YOLOv8](https://docs.ultralytics.com/)

---

## License

This project is developed for academic research at CTU Prague, Faculty of Electrical Engineering.
