# Realtime YOLO detection workflow (FlightForge + ROS2)

Questa guida riduce al minimo i comandi per avviare:

1. FlightForge
2. Sessione simulator (`start.sh`)
3. Terminale già pronto per lanciare il nodo detection

---

## 1) Avvio rapido con un comando

Il comportamento del launcher è controllato dal file [tmux/one_drone/config/runtime_stack.yaml](tmux/one_drone/config/runtime_stack.yaml).

Da lì puoi decidere:

- quale nodo avviare automaticamente: `none`, `detection`, `triangulation`
- se aprire o no il plot dell'errore
- quanti droni spawnare: `1`, `2`, `3`

Lo script [tmux/one_drone/launch_realtime_stack.sh](tmux/one_drone/launch_realtime_stack.sh) funziona così:

- lancia FlightForge
- lancia `start.sh`
- apre un terzo terminale già pronto con ROS + workspace + `.venv`

Prerequisiti:

- `gnome-terminal` installato
- FlightForge presente nella directory giusta
- `.venv` già creato nel workspace

Dalla root del workspace:

```bash
cd ~/git/training/mrs_uav_flightforge_simulator
chmod +x ./tmux/one_drone/launch_realtime_stack.sh
./tmux/one_drone/launch_realtime_stack.sh
```

Se la tua installazione di FlightForge è in `~/Pliska_FlightForge`, non devi fare altro.

Se invece FlightForge è in un'altra cartella, ad esempio `~/FS/FlightForge_Linux_v_0_11_3/Linux`, usa:

```bash
cd ~/git/training/mrs_uav_flightforge_simulator
export FLIGHTFORGE_DIR=~/FS/FlightForge_Linux_v_0_11_3/Linux
./tmux/one_drone/launch_realtime_stack.sh
```

Cosa fa lo script:

- apre un terminale e lancia FlightForge (`mrs_flight_forge.sh`)
- apre un terminale e lancia `tmux/one_drone/start.sh`
- apre un terzo terminale con `ROS + local_setup + .venv` già attivi
- in base alla config YAML, avvia automaticamente il nodo scelto
- in base alla config YAML, apre `rqt_plot` sull'errore di posizione dopo un delay
- genera a runtime una sessione tmux e una config simulatore coerenti con `drone_count`

Nel terzo terminale esegui il nodo detection:

```bash
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_realtime_node.py
```

Oppure, se vuoi fare il test multi-view con triangolazione tra `uav1` e `uav2`, esegui:

```bash
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_multiview_triangulation_node.py
```

### Config rapida del launcher

Esempio di [tmux/one_drone/config/runtime_stack.yaml](tmux/one_drone/config/runtime_stack.yaml):

```yaml
launcher:
	auto_start_node: triangulation
	open_error_plot: true
	plot_delay_sec: 10

simulation:
	drone_count: 3
```

Valori ammessi:

- `auto_start_node`: `none`, `detection`, `triangulation`
- `open_error_plot`: `true` / `false`
- `drone_count`: `1`, `2`, `3`

Comportamento delle pose di spawn:

- con `drone_count: 3`, le pose restano esattamente quelle di [tmux/one_drone/config/simulator.yaml](tmux/one_drone/config/simulator.yaml)
- con `drone_count: 2`, i droni runtime sono `uav1` e `uav2`, ma vengono posizionati usando i blocchi base `uav1` e `uav3` del [tmux/one_drone/config/simulator.yaml](tmux/one_drone/config/simulator.yaml)
- con `drone_count: 1`, viene usato solo il blocco base `uav1`

Esempi:

Per avviare automaticamente la triangolazione con 3 droni:

```yaml
launcher:
	auto_start_node: triangulation
	open_error_plot: true
	plot_delay_sec: 10

simulation:
	drone_count: 3
```

Per avviare solo il nodo detection single-view con 1 drone:

```yaml
launcher:
	auto_start_node: detection
	open_error_plot: false
	plot_delay_sec: 10

simulation:
	drone_count: 1
```

Per non auto-avviare nessun nodo e tenere pronto solo il terminale:

```yaml
launcher:
	auto_start_node: none
	open_error_plot: false
	plot_delay_sec: 10

simulation:
	drone_count: 2
```

---

## 2) Comando separato per il nodo `test_yolov8`

Se vuoi lanciare solo il nodo YOLO test a mano:

```bash
source /opt/ros/jazzy/setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/local_setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/.venv/bin/activate
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_realtime_node.py
```

Se vuoi specificare esplicitamente il modello:

```bash
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_realtime_node.py \
	--ros-args \
	-p model_path:=/home/nello/datasets/uav_detector/20260227_174226/runs/detect/exp1/run1_debug2/weights/best.pt
```

---

## 3) Comando separato per il nodo multi-view con triangolazione

Questo nodo:

- legge `uav1/rgb/image_raw` e `uav2/rgb/image_raw`
- usa lo stesso modello YOLO su entrambi
- pubblica le immagini annotate su `/uav1/detection` e `/uav2/detection`
- triangola la posizione del target
- confronta la stima con la ground truth del target (`uav3` di default)

Comando:

```bash
source /opt/ros/jazzy/setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/local_setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/.venv/bin/activate
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_multiview_triangulation_node.py
```

Con modello esplicito:

```bash
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_multiview_triangulation_node.py \
	--ros-args \
	-p model_path:=/home/nello/datasets/uav_detector/20260227_174226/runs/detect/exp1/run1_debug2/weights/best.pt
```

Topic default usati dal nodo:

- immagini input:
	- `/uav1/rgb/image_raw`
	- `/uav2/rgb/image_raw`
- camera info:
	- `/uav1/rgb/camera_info`
	- `/uav2/rgb/camera_info`
- odometria osservatori:
	- `/uav1/hw_api/ground_truth`
	- `/uav2/hw_api/ground_truth`
- ground truth target:
	- `/uav3/hw_api/ground_truth`

Topic pubblicati:

- immagini detection:
	- `/uav1/detection`
	- `/uav2/detection`
- posa stimata:
	- `/target/pose_estimate`
	- `/target/odometry_estimate`
- posizione stimata semplice da plottare:
	- `/target/position_estimate`
- errore rispetto alla GT:
	- `/target/position_error`

---

## 4) Come vedere detection, stima ed errore in realtime

### Detection annotate

Verifica che le immagini annotate stiano uscendo:

```bash
ros2 topic hz /uav1/detection
ros2 topic hz /uav2/detection
```

### Posizione stimata del target

Stampa a schermo:

```bash
ros2 topic echo /target/position_estimate
```

Plot realtime con `rqt_plot`:

```bash
ros2 run rqt_plot rqt_plot \
	/target/position_estimate/vector/x \
	/target/position_estimate/vector/y \
	/target/position_estimate/vector/z
```

### Errore rispetto alla ground truth

Stampa a schermo:

```bash
ros2 topic echo /target/position_error
```

Plot realtime con `rqt_plot`:

```bash
ros2 run rqt_plot rqt_plot \
	/target/position_error/vector/x \
	/target/position_error/vector/y \
	/target/position_error/vector/z
```

Comando rapido aggiuntivo per aprire subito il plot della stima:

```bash
ros2 run rqt_plot rqt_plot \
	/target/position_estimate/vector/x \
	/target/position_estimate/vector/y \
	/target/position_estimate/vector/z
```

Comando rapido aggiuntivo per aprire subito il plot dell'errore:

```bash
ros2 run rqt_plot rqt_plot \
	/target/position_error/vector/x \
	/target/position_error/vector/y \
	/target/position_error/vector/z
```

### Pose e odometry complete

Se vuoi vedere i messaggi ROS completi:

```bash
ros2 topic echo /target/pose_estimate
ros2 topic echo /target/odometry_estimate
```

---

## 5) Override path (se la tua installazione cambia)

Puoi personalizzare i path con variabili ambiente:

```bash
export FLIGHTFORGE_DIR=~/Pliska_FlightForge
export FLIGHTFORGE_CMD=./mrs_flight_forge.sh
export ROS_SETUP=/opt/ros/jazzy/setup.bash
export LOCAL_SETUP=~/git/training/mrs_uav_flightforge_simulator/local_setup.bash
export VENV_ACTIVATE=~/git/training/mrs_uav_flightforge_simulator/.venv/bin/activate
./tmux/one_drone/launch_realtime_stack.sh
```

---

## 6) Avvio manuale (fallback)

Se vuoi farlo a mano, usa tre terminali.

Terminale A:

```bash
cd ~/FS/FlightForge_Linux_v_0_11_3/Linux
./mrs_flight_forge.sh
```

Terminale B:

```bash
cd ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone
./start.sh
```

Terminale C:

```bash
source /opt/ros/jazzy/setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/local_setup.bash
source ~/git/training/mrs_uav_flightforge_simulator/.venv/bin/activate
python ~/git/training/mrs_uav_flightforge_simulator/tmux/one_drone/dataset_tools/test_yolov8_realtime_node.py
```

---

## 7) Check rapido

```bash
ros2 topic hz /test_img
```

Se il topic pubblica, la detection realtime sta girando correttamente.

Per il nodo multi-view, i check rapidi più utili sono:

```bash
ros2 topic hz /uav1/detection
ros2 topic hz /uav2/detection
ros2 topic echo /target/position_estimate
ros2 topic echo /target/position_error
```

```bash
ros2 run rqt_plot rqt_plot \
  /target/position_error/vector/x \
  /target/position_error/vector/y \
  /target/position_error/vector/z
```