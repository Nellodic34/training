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

---

## [NUOVO] Dataset + training per Heading Estimation (CNN)

Questa sezione è separata dalla pipeline YOLO e serve a costruire un modello dedicato alla stima dell'heading del target a partire dal crop della bbox.

### Obiettivo

- Continuare a usare YOLO per detection bbox.
- Aggiungere una CNN separata che stima heading dal crop del target.
- Label heading ricavate automaticamente da ground truth (`target_odom_topic`).

### 1) Raccolta dataset heading

Usa il nuovo nodo:

`tmux/one_drone/dataset_tools/collect_heading_dataset_node.py`

Esempio:

```bash
python3 ./tmux/one_drone/dataset_tools/collect_heading_dataset_node.py \
  --ros-args \
  -p rgb_topic:=/uav1/rgb/image_raw \
  -p camera_info_topic:=/uav1/rgb/camera_info \
  -p depth_topic:=/uav1/depth/image_raw \
  -p observer_odom_topic:=/uav1/hw_api/ground_truth \
  -p target_odom_topic:=/uav3/hw_api/ground_truth \
  -p output_dir:=/home/$USER/datasets/uav_heading \
  -p sample_every_n_frames:=5 \
  -p target_diameter_m:=0.8 \
  -p bbox_scale:=1.25 \
  -p crop_expand_scale:=1.2 \
  -p occlusion_check_enabled:=true \
  -p debug_labeled_images:=true
```

### 2) Output heading dataset

Per ogni run (`output_dir/<timestamp>/`):

- `crops/train|val/*.jpg` → input della CNN
- `labels/train|val/*.txt` → label per sample:
  - `yaw_camera_rad sin(yaw_camera) cos(yaw_camera) yaw_world_rad yaw_relative_world_rad`
- `metadata.csv` → tabella completa (bbox, split, percorsi file, yaw)
- opzionale `images/train|val/*.jpg` se `save_full_image:=true`

### 3) Training CNN heading

Script:

`tmux/one_drone/dataset_tools/train_heading_cnn.py`

Esempio training:

```bash
python3 ./tmux/one_drone/dataset_tools/train_heading_cnn.py \
  --dataset_root /home/$USER/datasets/uav_heading/<timestamp_run> \
  --output_dir /home/$USER/datasets/uav_heading_models \
  --epochs 30 \
  --batch_size 64 \
  --image_size 160 \
  --backbone resnet18
```

Output training:

- `best_heading_cnn.pt` → modello migliore (in base a `val_mae_deg`)
- `summary.json` → metriche finali e path
- `history.json` → curve per epoca

### 4) Come usarlo insieme a YOLO

Pipeline consigliata runtime:

1. YOLO → bbox target.
2. Crop bbox (con piccolo margine, es. 1.2x).
3. CNN heading → `sin/cos`, poi `yaw = atan2(sin, cos)`.
4. Fusione nel tracker (KF/IMM) insieme a posizione/velocità triangolate.

Nota: il dataset detection fornito esternamente resta utile per YOLO; il dataset heading raccolto in simulazione serve solo al modulo heading.






### 5) Setup ambiente Python (PEP668-safe, consigliato)

Su Ubuntu recente (`externally-managed-environment`) usa un virtual environment locale invece di `pip --user`.

Da `tmux/one_drone/`:

```bash
python3 -m venv .venv_heading
source .venv_heading/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r ./dataset_tools/requirements_heading.txt
```

Verifica:

```bash
python -c "import torch, torchvision, numpy, PIL; print(torch.__version__, torchvision.__version__)"
python -c "import torch; print('cuda:', torch.cuda.is_available())"
```

Per usare gli script dopo l'installazione:

```bash
source .venv_heading/bin/activate
```

---

## [NUOVO] Evaluation predizione traiettoria (ADE/FDE)

Script:

`tmux/one_drone/dataset_tools/evaluate_prediction_node.py`

Calcola il mismatch tra la traiettoria predetta dal nodo multiview e la traiettoria realmente eseguita dal target usando la ground truth del drone target.

I confronti disponibili, nel setup corrente, sono:

- `prediction vs ground truth`:
  - ground truth: `/uav3/hw_api/ground_truth`
  - prediction proposed: `/target/predicted_trajectory`
  - prediction baseline opzionale: `/target/predicted_trajectory_baseline`
- `prediction vs traiettoria nota (modello)`:
  - il nodo ricostruisce la traiettoria teorica attesa usando i parametri della traiettoria target (offset + salita + cerchio)
  - calcola metriche separate rispetto a questo modello

Il nodo:

1. riceve una `nav_msgs/Path` predetta
2. aspetta che arrivi abbastanza ground truth futura
3. per ogni punto della traiettoria cerca la posizione GT con timestamp più vicino
4. calcola errore punto per punto in metri
5. salva metriche aggregate (vs GT e, opzionalmente, vs traiettoria nota) e, a fine esecuzione, genera tabella e plot riassuntivi
6. pubblica anche i path completi (ground truth e modello) per confronto visivo in RViz

Metriche principali:

- `ADE` = average displacement error lungo la traiettoria predetta
- `FDE` = final displacement error al punto finale dell'orizzonte
- `MAX error` = massimo errore osservato lungo la traiettoria predetta

Può valutare:

1. solo `proposed` (nuovo metodo)
2. `proposed` + `baseline` insieme (confronto diretto e miglioramento %)

### Artefatti generati

Durante l'esecuzione aggiorna periodicamente il file JSON.

Alla chiusura del nodo salva automaticamente:

- `output_json_path`: summary JSON aggiornato anche runtime
- `output_plot_path`: PNG con plot del mismatch prediction vs ground truth / modello
- `output_report_path`: report Markdown con tabella finale e worst cases
- `output_csv_path`: CSV con una riga per ogni traiettoria valutata

Se specifichi solo `output_json_path`, gli altri path vengono derivati automaticamente dallo stesso prefisso.

Di default gli output non vanno più in `/tmp`, ma in:

- `tmux/one_drone/debug/evaluation/`

### Esempio A: valuti solo il metodo proposto

```bash
python3 ./tmux/one_drone/dataset_tools/evaluate_prediction_node.py \
  --ros-args \
  -p gt_odom_topic:=/uav3/hw_api/ground_truth \
  -p proposed_path_topic:=/target/predicted_trajectory \
  -p output_json_path:=/tmp/eval_proposed.json
```

### Esempio B: confronto baseline vs proposed

```bash
python3 ./tmux/one_drone/dataset_tools/evaluate_prediction_node.py \
  --ros-args \
  -p gt_odom_topic:=/uav3/hw_api/ground_truth \
  -p proposed_path_topic:=/target/predicted_trajectory \
  -p baseline_path_topic:=/target/predicted_trajectory_baseline \
  -p output_json_path:=/tmp/eval_compare.json
```

### Esempio C: output espliciti per report, plot e CSV

```bash
python3 ./tmux/one_drone/dataset_tools/evaluate_prediction_node.py \
  --ros-args \
  -p gt_odom_topic:=/uav3/hw_api/ground_truth \
  -p proposed_path_topic:=/target/predicted_trajectory \
  -p output_json_path:=/tmp/eval_multiview.json \
  -p output_plot_path:=/tmp/eval_multiview_plot.png \
  -p output_report_path:=/tmp/eval_multiview_report.md \
  -p output_csv_path:=/tmp/eval_multiview_samples.csv
```

### Modalità semplice consigliata (debug locale, no `/tmp`)

Da `tmux/one_drone`:

```bash
./run_prediction_evaluation.sh
```

Lo script:

- crea una run timestampata in `tmux/one_drone/debug/evaluation/<timestamp>/`
- aggiorna il link `tmux/one_drone/debug/evaluation/latest`
- a fine esecuzione (`Ctrl+C`) apre automaticamente plot e report

Visualizzazione rapida dei file dell'ultima run:

```bash
ls -lh ./debug/evaluation/latest
xdg-open ./debug/evaluation/latest/prediction_eval_plot.png
xdg-open ./debug/evaluation/latest/prediction_eval_report.md
column -s, -t ./debug/evaluation/latest/prediction_eval_samples.csv | less -S
cat ./debug/evaluation/latest/prediction_eval.json
```

### Parametri principali

- `gt_odom_topic`: topic `Odometry` della traiettoria reale del target
- `proposed_path_topic`: topic `Path` della prediction del metodo proposto
- `baseline_path_topic`: topic `Path` della prediction baseline
- `stamp_tolerance_sec`: tolleranza massima per match temporale prediction↔GT
- `max_pending_age_sec`: tempo massimo di attesa prima di scartare una prediction non valutabile
- `report_every_n_paths`: ogni quante traiettorie stampare un riepilogo su terminale
- `output_json_path`: summary JSON
- `output_dir`: directory base per output (default `tmux/one_drone/debug/evaluation`)
- `output_plot_path`: PNG finale con plot del mismatch
- `output_xy_plot_path`: PNG dedicato al confronto XY (circonferenza nota vs predizioni)
- `output_report_path`: report Markdown finale
- `output_csv_path`: CSV finale per analisi offline
- `enable_known_trajectory_model`: abilita confronto prediction vs traiettoria teorica nota
- `model_initial_offset_x`, `model_initial_offset_z`, `model_pre_circle_climb_z`, `model_circle_radius`, `model_transition_speed`, `model_speed`: parametri del modello di traiettoria nota (devono rispecchiare il nodo che comanda il target)
- `plot_observer_markers`: abilita i marker delle pose observer nel PNG XY dedicato
- `observer1_odom_topic`, `observer2_odom_topic`: topic `Odometry` usati per disegnare i segnalini observer nel grafico XY

### Cosa trovi nei file finali

#### JSON

Contiene:

- `proposed/baseline` + `improvement_percent` per `prediction vs ground truth` (solo fase circolare)
- `known_trajectory_model.proposed/baseline` + `known_trajectory_model.improvement_percent` per `prediction vs modello noto` (solo fase circolare)
- `ground_truth_vs_known_trajectory` per verificare quanto la traiettoria reale segua il modello atteso
- `artifacts.*` con i path dei file generati

#### PNG

Mostra:

- overlay XY della sola fase circolare tra traiettoria predetta, ground truth e modello noto
- errore di posizione nel tempo (fase circolare) con ADE/FDE/RMSE
- errore medio di predizione su orizzonte temporale (fase circolare)
- errore medio di velocità su orizzonte temporale (fase circolare)
- coerenza del raggio nel tempo (ground truth vs predetto)
- tabella finale sintetica nel pannello riassuntivo

#### PNG XY dedicato

Mostra:

- circonferenza teorica nota (fase circolare)
- nuvola delle traiettorie predette `proposed` valutate
- evidenza dell'ultima predizione
- segnalini della posa observer (`observer1`, `observer2`) se i topic sono disponibili

#### Markdown report

Contiene:

- tabella finale delle metriche aggregate vs ground truth (ADE/FDE/MAX + RMSE posizione + RMSE velocità)
- tabella finale delle metriche aggregate vs traiettoria modello nota (ADE/FDE/MAX + RMSE posizione + RMSE velocità)
- miglioramento % vs baseline (quando disponibile)
- top dei casi peggiori ordinati per `ADE`
- nota esplicita che metriche/grafici sono limitati alla fase circolare


#### CSV

Una riga per ogni prediction valutata con:

- `source`
- `comparison` (`ground_truth` oppure `known_trajectory_model`)
- `sample_index`
- `created_time_sec`
- `horizon_points`
- `ade_m`
- `fde_m`
- `max_error_m`
- `position_rmse_m`
- `velocity_rmse_m`

### Procedura consigliata d'uso

1. avvia la simulazione e il nodo multiview
2. verifica che stiano pubblicando:
   - `/uav3/hw_api/ground_truth`
   - `/target/predicted_trajectory`
3. lancia l'evaluator in un terminale separato
4. lascia girare lo scenario abbastanza a lungo da raccogliere più traiettorie
5. interrompi il nodo con `Ctrl+C`
6. apri i file generati (`.json`, `.png`, `.md`, `.csv`)
  - incluso il file XY dedicato: `prediction_eval_xy.png`
7. in RViz aggiungi/abilita:
  - predicted trajectory markers (già presenti nel tuo stack)
  - path completo modello noto pubblicato dal nodo traiettoria: `/target/known_trajectory_path`

### Come leggere il risultato

- `ADE` basso = prediction buona mediamente lungo tutto l'orizzonte
- `RMSE posizione` basso = errore globale ridotto sulla fase circolare
- `RMSE velocità` basso = dinamica predetta coerente con quella reale
- `FDE` basso = prediction buona sul punto finale, quindi utile se ti interessa dove sarà il target a fine orizzonte
- `MAX error` basso = prediction stabile senza grossi picchi
- `improvement_percent > 0` = il metodo `proposed` è migliore del `baseline`

Per confronto tesi pulito:

1. lancia stessi scenari (seed, traiettorie target, durata)
2. raccogli metriche baseline
3. raccogli metriche proposed
4. confronta anche i plot XY e i worst cases del report
5. riporta miglioramento `%` su ADE/FDE/MAX error


#Workflow addestramento YOLO

ros2 run trajectory_planner uav_simple_traj --ros-args -p uav_name:=uav2

python3 collect_yolo_dataset_node.py --ros-args \
  -p output_dir:=$HOME/datasets/uav_detector \

yolo detect train \
  data=$HOME/dataset_merged/dataset.yaml \
  model=yolov8n.pt \
  imgsz=960 \
  epochs=100 \
  batch=16 \
  name=drone_detector_n_960

yolo detect val \
  data=$HOME/dataset_merged/dataset.yaml \
  model=runs/detect/drone_detector_n_960/weights/best.pt \
  imgsz=960

il deploy va modificato nel file triangulation
yolo export model=runs/detect/drone_detector_n_960/weights/best.pt format=onnx imgsz=960