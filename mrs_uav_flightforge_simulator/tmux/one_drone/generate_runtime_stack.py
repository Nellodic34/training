#!/usr/bin/env python3

from copy import deepcopy
import os
from pathlib import Path
import shlex
import sys

import yaml


AVAILABLE_UAVS = ['uav1', 'uav2', 'uav3']


def get_runtime_uav_mapping(drone_count: int):
    if drone_count == 1:
        return [('uav1', 'uav1')]
    if drone_count == 2:
        return [('uav1', 'uav1'), ('uav2', 'uav3')]
    if drone_count == 3:
        return [('uav1', 'uav1'), ('uav2', 'uav2'), ('uav3', 'uav3')]
    raise ValueError('simulation.drone_count must be 1, 2 or 3')


def shell_quote(value) -> str:
    return shlex.quote(str(value))


def build_dataset_tool_command(
    workspace_dir: Path,
    ros_setup: str,
    local_setup: str,
    venv_activate: str,
    python_bin: str,
    script_path: str,
    intro_message: str,
    ros_parameters=None,
):
    ros_parameters = ros_parameters or {}
    ros_args = ''
    if ros_parameters:
        ros_args = ' --ros-args ' + ' '.join(
            f"-p {shell_quote(f'{name}:={value}')}" for name, value in ros_parameters.items()
        )

    return (
        ' && '.join(
            [
                f'cd {shell_quote(workspace_dir)}',
                f'source {shell_quote(ros_setup)}',
                f'source {shell_quote(local_setup)}',
                f'source {shell_quote(venv_activate)}',
                f'echo {shell_quote(intro_message)}',
                f'{shell_quote(python_bin)} {shell_quote(script_path)}{ros_args}',
            ]
        )
        + '; exec bash'
    )


def build_ready_command(
    workspace_dir: Path,
    ros_setup: str,
    local_setup: str,
    venv_activate: str,
    detection_script: str,
    triangulation_script: str,
):
    return (
        ' && '.join(
            [
                f'cd {shell_quote(workspace_dir)}',
                f'source {shell_quote(ros_setup)}',
                f'source {shell_quote(local_setup)}',
                f'source {shell_quote(venv_activate)}',
                "echo 'Environment ready for detection and triangulation nodes.'",
                f"echo 'Single-view detection: python {detection_script}'",
                f"echo 'Multi-view triangulation: python {triangulation_script}'",
            ]
        )
        + '; exec bash'
    )


def build_auto_start_window(node_cfg):
    workspace_dir = Path(node_cfg['workspace_dir'])
    ros_setup = node_cfg['ros_setup']
    local_setup = node_cfg['local_setup']
    venv_activate = node_cfg['venv_activate']
    python_bin = node_cfg['python_bin']
    detection_script = node_cfg['detection_script']
    triangulation_script = node_cfg['triangulation_script']
    auto_start_node = node_cfg['auto_start_node']

    if auto_start_node == 'triangulation':
        triangulation_params = {
            'observer1_name': node_cfg['observer1_name'],
            'observer2_name': node_cfg['observer2_name'],
            'target_name': node_cfg['target_name'],
            'kf_process_noise_acc': node_cfg['kf_process_noise_acc'],
            'kf_measurement_noise': node_cfg['kf_measurement_noise'],
            'kf_initial_covariance': node_cfg['kf_initial_covariance'],
        }
        return {
            'triangulation': {
                'layout': 'tiled',
                'panes': [
                    build_dataset_tool_command(
                        workspace_dir,
                        ros_setup,
                        local_setup,
                        venv_activate,
                        python_bin,
                        triangulation_script,
                        'Starting multi-view triangulation node...',
                        triangulation_params,
                    )
                ],
            }
        }

    if auto_start_node == 'detection':
        return {
            'detection': {
                'layout': 'tiled',
                'panes': [
                    build_dataset_tool_command(
                        workspace_dir,
                        ros_setup,
                        local_setup,
                        venv_activate,
                        python_bin,
                        detection_script,
                        'Starting single-view detection node...',
                    )
                ],
            }
        }

    if auto_start_node == 'decentralized':
        observer_script = node_cfg['observer_script']
        main_script = node_cfg['main_triangulation_script']
        
        observer_params = {
            'uav_name': node_cfg['observer2_name']
        }
        main_params = {
            'uav_name': node_cfg['observer1_name'],
            'observer1_name': node_cfg['observer2_name'],
            'target_name': node_cfg['target_name'],
            'kf_process_noise_acc': node_cfg['kf_process_noise_acc'],
            'kf_measurement_noise': node_cfg['kf_measurement_noise'],
            'kf_initial_covariance': node_cfg['kf_initial_covariance'],
        }
        
        return {
            'decentralized': {
                'layout': 'tiled',
                'panes': [
                    build_dataset_tool_command(
                        workspace_dir,
                        ros_setup,
                        local_setup,
                        venv_activate,
                        python_bin,
                        main_script,
                        'Starting Main Triangulation node...',
                        main_params,
                    ),
                    build_dataset_tool_command(
                        workspace_dir,
                        ros_setup,
                        local_setup,
                        venv_activate,
                        python_bin,
                        observer_script,
                        'Starting Observer node...',
                        observer_params,
                    )
                ],
            }
        }

    return {
        'perception_ready': {
            'layout': 'tiled',
            'panes': [
                build_ready_command(
                    workspace_dir,
                    ros_setup,
                    local_setup,
                    venv_activate,
                    detection_script,
                    triangulation_script,
                )
            ],
        }
    }


def build_session(root_dir: Path, enabled_uavs, flightforge_dir: str, flightforge_cmd: str, node_cfg):
    session = {
        'root': str(root_dir),
        'name': 'simulation',
        'socket_name': 'mrs',
        'attach': False,
        'tmux_options': '-f /etc/ctu-mrs/tmux.conf',
        'startup_window': 'status',
        'pre_window': [
            'export USE_SIM_TIME="true"',
            'export RUN_TYPE=simulation',
            'export UAV_TYPE=x500',
            'export PLATFORM_CONFIG=`ros2 pkg prefix mrs_multirotor_simulator`/share/mrs_multirotor_simulator/config/mrs_uav_system/$UAV_TYPE.yaml',
            'export RMW_IMPLEMENTATION=rmw_zenoh_cpp',
        ],
        'windows': [],
    }

    session['windows'].append(
        {
            'flightforge': {
                'layout': 'tiled',
                'panes': [f'cd {flightforge_dir} && {flightforge_cmd}'],
            }
        }
    )
    session['windows'].append({'router': {'layout': 'tiled', 'panes': ['ros2 run rmw_zenoh_cpp rmw_zenohd']}})
    session['windows'].append(
        {
            'simulator': {
                'layout': 'tiled',
                'panes': [
                    'ros2 launch mrs_uav_flightforge_simulator flightforge_simulator.launch.py custom_config:=./config/generated/simulator.runtime.yaml'
                ],
            }
        }
    )

    def one_line(command_prefix: str, command: str):
        return f'export UAV_NAME={command_prefix}; {command}'

    def core_command(uav: str):
        return ' '.join(
            [
                f'export UAV_NAME={uav};',
                'waitForHwApi; sleep 10;',
                'ros2 launch mrs_uav_core core.launch.py',
                'platform_config:=$PLATFORM_CONFIG',
                'world_config:=./config/world_config.yaml',
                'custom_config:=./config/custom_config.yaml',
                'network_config:=./config/generated/network_config.runtime.yaml',
            ]
        )

    session['windows'].append(
        {
            'hw_api': {
                'layout': 'tiled',
                'panes': [
                    one_line(uav, 'ros2 launch mrs_uav_flightforge_simulator hw_api.launch.py') for uav in enabled_uavs
                ],
            }
        }
    )
    session['windows'].append(
        {
            'status': {
                'layout': 'tiled',
                'panes': [one_line(uav, 'ros2 run mrs_uav_status status.sh') for uav in enabled_uavs],
            }
        }
    )
    session['windows'].append(
        {
            'core': {
                'layout': 'tiled',
                'panes': [core_command(uav) for uav in enabled_uavs],
            }
        }
    )
    session['windows'].append(
        {
            'autostart': {
                'layout': 'tiled',
                'panes': [
                    one_line(
                        uav,
                        'ros2 launch mrs_uav_autostart automatic_start.launch.py custom_config:=./config/automatic_start.yaml',
                    )
                    for uav in enabled_uavs
                ],
            }
        }
    )
    session['windows'].append(
        {
            'takeoff': {
                'layout': 'tiled',
                'panes': [one_line(uav, 'waitForCore; sleep 10; ./takeoff.sh') for uav in enabled_uavs],
            }
        }
    )
    session['windows'].append(
        {
            'stereo': {
                'layout': 'tiled',
                'panes': [
                    one_line(uav, f'ros2 launch stereo_image_proc stereo_image_proc.launch.py namespace:={uav}/stereo')
                    for uav in enabled_uavs
                ],
            }
        }
    )
    session['windows'].append(build_auto_start_window(node_cfg))

    session['windows'].append(
        {
            'rviz': {
                'layout': 'tiled',
                'panes': [
                    'export UAV_NAME=uav1; waitForCore; ros2 run rviz2 rviz2 -d ./rviz.rviz --ros-args -p use_sim_time:=true'
                ],
            }
        }
    )
    session['windows'].append({'reconfigure': {'layout': 'tiled', 'panes': ['ros2 run rqt_reconfigure rqt_reconfigure']}})
    session['windows'].append(
        {
            'layout': {
                'layout': 'tiled',
                'panes': ['export UAV_NAME=uav1; waitForCore; sleep 5; ~/.i3/layout_manager.sh ./layout.json'],
            }
        }
    )
    session['windows'].append({'rqt': {'layout': 'tiled', 'panes': ['rqt']}})
    session['windows'].append({'recording': {'layout': 'tiled', 'panes': ['']}})
    return session


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    config_dir = script_dir / 'config'
    generated_dir = script_dir / 'generated'
    generated_config_dir = config_dir / 'generated'
    generated_dir.mkdir(exist_ok=True)
    generated_config_dir.mkdir(exist_ok=True)

    runtime_config_path = Path(os.environ.get('RUNTIME_STACK_CONFIG_PATH', str(config_dir / 'runtime_stack.yaml')))
    simulator_base_path = config_dir / 'simulator.yaml'
    network_base_path = config_dir / 'network_config.yaml'

    runtime_config = yaml.safe_load(runtime_config_path.read_text(encoding='utf-8')) or {}
    launcher_cfg = runtime_config.get('launcher', {})
    simulation_cfg = runtime_config.get('simulation', {})
    ekf_cfg = runtime_config.get('ekf', {})

    auto_start_node = str(os.environ.get('AUTO_START_NODE_OVERRIDE', launcher_cfg.get('auto_start_node', 'triangulation'))).strip().lower()
    if auto_start_node not in {'none', 'detection', 'triangulation', 'decentralized'}:
        raise ValueError('launcher.auto_start_node must be one of: none, detection, triangulation, decentralized')

    open_error_plot = bool(launcher_cfg.get('open_error_plot', True))
    plot_delay_sec = int(launcher_cfg.get('plot_delay_sec', 10))

    uav_roles_cfg = runtime_config.get('uav_roles', {})
    observer1_name = str(uav_roles_cfg.get('observer1', 'uav1'))
    observer2_name = str(uav_roles_cfg.get('observer2', 'uav2'))
    target_name = str(uav_roles_cfg.get('target', 'uav3'))
    kf_process_noise_acc = float(ekf_cfg.get('kf_process_noise_acc', 1.0))
    kf_measurement_noise = float(ekf_cfg.get('kf_measurement_noise', 0.05))
    kf_initial_covariance = float(ekf_cfg.get('kf_initial_covariance', 10.0))

    flightforge_dir = os.environ.get('FLIGHTFORGE_DIR', str(Path.home() / 'Pliska_FlightForge'))
    flightforge_cmd = os.environ.get('FLIGHTFORGE_CMD', './mrs_flight_forge.sh')
    workspace_dir = script_dir.parent.parent
    ros_setup = os.environ.get('ROS_SETUP', '/opt/ros/jazzy/setup.bash')
    local_setup = os.environ.get('LOCAL_SETUP', str(workspace_dir / 'local_setup.bash'))
    venv_activate = os.environ.get('VENV_ACTIVATE', str(workspace_dir / '.venv/bin/activate'))
    python_bin = os.environ.get('PYTHON_BIN', str(workspace_dir / '.venv/bin/python'))
    detection_script = os.environ.get(
        'DETECTION_SCRIPT',
        str(script_dir / 'dataset_tools/test_yolov8_realtime_node.py'),
    )
    triangulation_script = os.environ.get(
        'TRIANGULATION_SCRIPT',
        str(script_dir / 'dataset_tools/test_yolov8_multiview_triangulation_node.py'),
    )
    observer_script = os.environ.get(
        'OBSERVER_SCRIPT',
        str(script_dir / 'dataset_tools/yolov8_observer_node.py'),
    )
    main_triangulation_script = os.environ.get(
        'MAIN_TRIANGULATION_SCRIPT',
        str(script_dir / 'dataset_tools/yolov8_main_triangulation_node.py'),
    )

    drone_count = int(simulation_cfg.get('drone_count', 3))
    if drone_count not in {1, 2, 3}:
        raise ValueError('simulation.drone_count must be 1, 2 or 3')

    runtime_uav_mapping = get_runtime_uav_mapping(drone_count)
    enabled_uavs = [runtime_name for runtime_name, _ in runtime_uav_mapping]

    simulator_base = yaml.safe_load(simulator_base_path.read_text(encoding='utf-8'))
    simulator_runtime = deepcopy(simulator_base)
    simulator_runtime['uav_names'] = enabled_uavs

    for uav in AVAILABLE_UAVS:
        simulator_runtime.pop(uav, None)

    for runtime_name, source_name in runtime_uav_mapping:
        if source_name not in simulator_base:
            raise KeyError(f'Missing UAV block in simulator base config: {source_name}')
        simulator_runtime[runtime_name] = deepcopy(simulator_base[source_name])

    network_base = yaml.safe_load(network_base_path.read_text(encoding='utf-8'))
    network_runtime = deepcopy(network_base)
    network_runtime.setdefault('network', {})['robot_names'] = enabled_uavs

    node_cfg = {
        'workspace_dir': workspace_dir,
        'ros_setup': ros_setup,
        'local_setup': local_setup,
        'venv_activate': venv_activate,
        'python_bin': python_bin,
        'detection_script': detection_script,
        'triangulation_script': triangulation_script,
        'observer_script': observer_script,
        'main_triangulation_script': main_triangulation_script,
        'auto_start_node': auto_start_node,
        'observer1_name': observer1_name,
        'observer2_name': observer2_name,
        'target_name': target_name,
        'kf_process_noise_acc': kf_process_noise_acc,
        'kf_measurement_noise': kf_measurement_noise,
        'kf_initial_covariance': kf_initial_covariance,
    }

    session_runtime = build_session(script_dir, enabled_uavs, flightforge_dir, flightforge_cmd, node_cfg)

    simulator_runtime_path = generated_config_dir / 'simulator.runtime.yaml'
    network_runtime_path = generated_config_dir / 'network_config.runtime.yaml'
    session_runtime_path = generated_dir / 'session.runtime.yml'
    env_path = generated_dir / 'runtime.env'

    simulator_runtime_path.write_text(yaml.safe_dump(simulator_runtime, sort_keys=False), encoding='utf-8')
    network_runtime_path.write_text(yaml.safe_dump(network_runtime, sort_keys=False), encoding='utf-8')
    session_runtime_path.write_text(yaml.safe_dump(session_runtime, sort_keys=False), encoding='utf-8')

    env_path.write_text(
        '\n'.join(
            [
                f"GENERATED_SESSION_YML_PATH='{session_runtime_path}'",
                f"AUTO_START_NODE='{auto_start_node}'",
                f"OPEN_ERROR_PLOT='{'true' if open_error_plot else 'false'}'",
                f"PLOT_DELAY_SEC='{plot_delay_sec}'",
                f"DRONE_COUNT='{drone_count}'",
                f"OBSERVER1_NAME='{observer1_name}'",
                f"OBSERVER2_NAME='{observer2_name}'",
                f"TARGET_NAME='{target_name}'",
                f"KF_PROCESS_NOISE_ACC='{kf_process_noise_acc}'",
                f"KF_MEASUREMENT_NOISE='{kf_measurement_noise}'",
                f"KF_INITIAL_COVARIANCE='{kf_initial_covariance}'",
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    mapping_str = ', '.join([f'{runtime}->{source}' for runtime, source in runtime_uav_mapping])
    print(f'Generated runtime stack for {drone_count} drone(s): {mapping_str}')
    print(f'Session: {session_runtime_path}')
    print(f'Simulator config: {simulator_runtime_path}')
    print(f'Network config: {network_runtime_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
