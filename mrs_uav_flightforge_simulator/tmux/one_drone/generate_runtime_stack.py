#!/usr/bin/env python3

from copy import deepcopy
import os
from pathlib import Path
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


def build_session(root_dir: Path, enabled_uavs):
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

    auto_start_node = str(launcher_cfg.get('auto_start_node', 'triangulation')).strip().lower()
    if auto_start_node not in {'none', 'detection', 'triangulation'}:
        raise ValueError('launcher.auto_start_node must be one of: none, detection, triangulation')

    open_error_plot = bool(launcher_cfg.get('open_error_plot', True))
    plot_delay_sec = int(launcher_cfg.get('plot_delay_sec', 10))

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

    session_runtime = build_session(script_dir, enabled_uavs)

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
