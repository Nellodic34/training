# Dataset tools for UAV detector

Questo tool crea un dataset in formato YOLO (`images/train|val` + `labels/train|val`) usando solo topic stabili:
- RGB della camera osservatrice (`/uav1/rgb/image_raw`)
- Camera intrinsics (`/uav1/rgb/camera_info`)
- Ground truth odometry osservatore (`/uav1/hw_api/ground_truth`)
- Ground truth odometry target (`/uav2/hw_api/ground_truth`)

Le bbox sono stimate via proiezione geometrica 3D->2D, quindi non dipendono dalla segmentation.

## 1) Prerequisiti

Assicurati che nella config simulatore ci siano:
- `mrs_uav_flightforge_simulator.sensors.rgb.enabled: true`
- `mrs_uav_flightforge_simulator.sensors.rgb.depth.enabled: true` (per filtro occlusioni)
- `publishers.odometry.enabled: true` (nel simulatore)
- `ground_truth: true` (in hw_api, già presente nella tua repo)

## 2) Avvio simulazione

1. Avvia FlightForge
2. Avvia sessione tmux: `./tmux/one_drone/start.sh`
3. Lascia partire i nodi `hw_api/core` dei due UAV

## 3) Quando avviare il nodo dataset

Avvialo quando:
- `uav1` (camera) è fermo nella posa desiderata
- `uav2` sta per iniziare il moto per la raccolta

In pratica: avvialo subito prima della traiettoria di `uav2`, e fermalo a fine raccolta.

## 4) Avvio dataset node

In un nuovo terminale (con environment ROS già sourciato):

```bash
python3 ./tmux/one_drone/dataset_tools/collect_yolo_dataset_node.py \
  --ros-args \
  -p rgb_topic:=/uav1/rgb/image_raw \
  -p camera_info_topic:=/uav1/rgb/camera_info \
  -p depth_topic:=/uav1/depth/image_raw \
  -p observer_odom_topic:=/uav1/hw_api/ground_truth \
  -p target_odom_topic:=/uav2/hw_api/ground_truth \
  -p output_dir:=/home/$USER/datasets/uav_detector \
  -p debug_labeled_images:=true \
  -p debug_output_dir:=/home/nello/data_test \
  -p camera_offset_xyz_m:="[0.118, 0.0, 0.016]" \
  -p target_diameter_m:=0.8 \
  -p bbox_scale:=1.25 \
  -p occlusion_check_enabled:=true \
  -p occlusion_margin_m:=0.35 \
  -p sample_every_n_frames:=5 \
  -p save_negative_samples:=true
```

Nota: a ogni avvio viene creata automaticamente una sottocartella con timestamp (es. `20260227_154500`) sia dentro `output_dir` sia dentro `debug_output_dir`.

## 5) Output

Struttura generata (per singolo run):

- `output_dir/<timestamp>/images/train/*.jpg`
- `output_dir/<timestamp>/images/val/*.jpg`
- `output_dir/<timestamp>/labels/train/*.txt`
- `output_dir/<timestamp>/labels/val/*.txt`
- `output_dir/<timestamp>/dataset.yaml`
- `debug_output_dir/<timestamp>/train/*.jpg` e `debug_output_dir/<timestamp>/val/*.jpg` (immagini con bbox disegnata)

Ogni label è nel formato YOLO:

`class_id x_center y_center width height`

Valori normalizzati in `[0,1]`.

## 6) Note pratiche

- Se le bbox risultano strette/larghe, regola `target_diameter_m` e `bbox_scale`.
- Se perdi frame, alza `sample_every_n_frames`.
- Se vuoi solo esempi positivi, usa `-p save_negative_samples:=false`.
- Per disabilitare il salvataggio immagini di controllo, usa `-p debug_labeled_images:=false`.
- Se la depth non è disponibile o è rumorosa, il filtro occlusioni viene bypassato o puoi disabilitarlo con `-p occlusion_check_enabled:=false`.
- Per x500 il valore iniziale consigliato è `target_diameter_m=0.8`, derivato da `arm_length=0.25` e `prop_radius=0.15` nel file `/opt/ros/jazzy/share/mrs_multirotor_simulator/config/uavs/x500.yaml` (diametro approssimato `2*(arm_length+prop_radius)`).

