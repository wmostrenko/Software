import os

from typing import Any, Optional

from software.py_constants import *
from proto.import_all_protos import *
from software.thunderscope.common.fps_widget import FPSWidget
from software.thunderscope.common.frametime_counter import FrameTimeCounter
from software.thunderscope.common.proto_plotter import ProtoPlotter
from software.thunderscope.gl.layers.gl_draw_polygon_obstacle import (
    GLDrawPolygonObstacleLayer,
)
from software.thunderscope.proto_unix_io import ProtoUnixIO
from proto.robot_log_msg_pb2 import RobotLog
from extlibs.er_force_sim.src.protobuf.world_pb2 import *
from software.thunderscope.dock_style import *

# Import Widgets
from software.thunderscope.gl.gl_widget import GLWidget
from software.thunderscope.gl.layers import (
    gl_obstacle_layer,
    gl_path_layer,
    gl_validation_layer,
    gl_passing_layer,
    gl_attacker_layer,
    gl_sandbox_world_layer,
    gl_world_layer,
    gl_debug_shapes_layer,
    gl_simulator_layer,
    gl_tactic_layer,
    gl_cost_vis_layer,
    gl_trail_layer,
    gl_movement_field_test_layer,
    gl_max_dribble_layer,
    gl_referee_info_layer,
)

from software.thunderscope.common.proto_configuration_widget import (
    ProtoConfigurationWidget,
)
from software.thunderscope.log.g3log_widget import g3logWidget
from software.thunderscope.constants import IndividualRobotMode
from software.thunderscope.play.playinfo_widget import PlayInfoWidget
from software.thunderscope.play.refereeinfo_widget import RefereeInfoWidget
from software.thunderscope.robot_diagnostics.diagnostics_widget import DiagnosticsWidget
from software.thunderscope.robot_diagnostics.robot_view import RobotView
from software.thunderscope.robot_diagnostics.robot_error_log import RobotErrorLog
from software.thunderscope.robot_diagnostics.estop_view import EstopView
from software.thunderscope.replay.proto_player import ProtoPlayer


################################
#  FULLSYSTEM RELATED WIDGETS  #
################################


def setup_gl_widget(
    sim_proto_unix_io: ProtoUnixIO,
    full_system_proto_unix_io: ProtoUnixIO,
    friendly_colour_yellow: bool,
    visualization_buffer_size: int,
    sandbox_mode: bool = False,
    replay: bool = False,
    replay_log: os.PathLike = None,
    frame_swap_counter: Optional[FrameTimeCounter] = None,
    send_sync_message: bool = False,
) -> Field:
    """Setup the GLWidget with its constituent layers

    :param sim_proto_unix_io: The proto unix io object for the simulator
    :param full_system_proto_unix_io: The proto unix io object for the full system
    :param friendly_colour_yellow: Whether the friendly colour is yellow
    :param visualization_buffer_size: How many packets to buffer while rendering
    :param sandbox_mode: if sandbox mode should be enabled
    :param replay: Whether replay mode is currently enabled
    :param replay_log: The file path of the replay log
    :param frame_swap_counter: FrameTimeCounter to keep track of the time between
                               frame swaps in the GLWidget
    :param send_sync_message: Whether to synchronize Thunderscope with a listener
    :return: The GLWidget
    """
    # Create ProtoPlayer if replay is enabled
    player = ProtoPlayer(replay_log, full_system_proto_unix_io) if replay else None

    # Create widget
    gl_widget = GLWidget(
        proto_unix_io=full_system_proto_unix_io,
        friendly_color_yellow=friendly_colour_yellow,
        frame_swap_counter=frame_swap_counter,
        player=player,
        sandbox_mode=sandbox_mode,
    )

    # Create layers
    validation_layer = gl_validation_layer.GLValidationLayer(
        "Validation", visualization_buffer_size
    )
    path_layer = gl_path_layer.GLPathLayer("Paths", visualization_buffer_size)

    obstacle_layer = gl_obstacle_layer.GLObstacleLayer(
        "Obstacles", visualization_buffer_size
    )
    debug_shapes_layer = gl_debug_shapes_layer.GLDebugShapesLayer(
        "Debug Shapes", visualization_buffer_size
    )
    passing_layer = gl_passing_layer.GLPassingLayer(
        "Passing", visualization_buffer_size
    )
    attacker_layer = gl_attacker_layer.GLAttackerLayer(
        "Attacker Tactic", visualization_buffer_size
    )
    cost_vis_layer = gl_cost_vis_layer.GLCostVisLayer(
        "Passing Cost", visualization_buffer_size
    )
    world_layer = (
        gl_sandbox_world_layer.GLSandboxWorldLayer(
            "Vision",
            sim_proto_unix_io,
            friendly_colour_yellow,
            visualization_buffer_size,
        )
        if sandbox_mode
        else gl_world_layer.GLWorldLayer(
            "Vision",
            sim_proto_unix_io,
            friendly_colour_yellow,
            visualization_buffer_size,
        )
    )
    field_movement_layer = gl_movement_field_test_layer.GLMovementFieldTestLayer(
        "Field Movement Layer", full_system_proto_unix_io
    )
    simulator_layer = gl_simulator_layer.GLSimulatorLayer(
        "Simulator", friendly_colour_yellow, visualization_buffer_size
    )
    tactic_layer = gl_tactic_layer.GLTacticLayer("Tactics", visualization_buffer_size)
    trail_layer = gl_trail_layer.GLTrailLayer("Trail", visualization_buffer_size)
    max_dribble_layer = gl_max_dribble_layer.GLMaxDribbleLayer(
        "Dribble Tracking", visualization_buffer_size
    )
    referee_layer = gl_referee_info_layer.GLRefereeInfoLayer(
        "Referee Info", visualization_buffer_size
    )

    draw_obstacle_layer = GLDrawPolygonObstacleLayer(
        "Draw Obstacle Layer", full_system_proto_unix_io
    )

    gl_widget.add_layer(world_layer)
    gl_widget.add_layer(simulator_layer, False)
    gl_widget.add_layer(path_layer)
    gl_widget.add_layer(obstacle_layer)
    gl_widget.add_layer(draw_obstacle_layer, False)
    gl_widget.add_layer(passing_layer)
    gl_widget.add_layer(attacker_layer)
    gl_widget.add_layer(cost_vis_layer, True)
    gl_widget.add_layer(tactic_layer, False)
    gl_widget.add_layer(validation_layer)
    gl_widget.add_layer(trail_layer, False)
    gl_widget.add_layer(debug_shapes_layer, True)
    gl_widget.add_layer(field_movement_layer, False)
    gl_widget.add_layer(max_dribble_layer, True)
    gl_widget.add_layer(referee_layer)

    simulation_control_toolbar = gl_widget.get_sim_control_toolbar()
    simulation_control_toolbar.set_speed_callback(world_layer.set_simulation_speed)

    # connect all sandbox controls if using sandbox mode
    if sandbox_mode:
        simulation_control_toolbar.undo_button.clicked.connect(world_layer.undo)
        simulation_control_toolbar.redo_button.clicked.connect(world_layer.redo)
        simulation_control_toolbar.reset_button.clicked.connect(
            world_layer.reset_to_pre_sim
        )
        world_layer.undo_toggle_enabled_signal.connect(
            simulation_control_toolbar.toggle_undo_enabled
        )
        world_layer.redo_toggle_enabled_signal.connect(
            simulation_control_toolbar.toggle_redo_enabled
        )
        simulation_control_toolbar.pause_button.clicked.connect(
            world_layer.toggle_play_state
        )
        sim_proto_unix_io.register_observer(
            SimulationState, simulation_control_toolbar.simulation_state_buffer
        )
        sim_proto_unix_io.register_observer(
            SimulationState, world_layer.simulation_state_buffer
        )
        sim_proto_unix_io.register_observer(
            SimulationState, gl_widget.simulation_state_buffer
        )

    for arg in [
        (World, world_layer.world_buffer),
        (World, cost_vis_layer.world_buffer),
        (World, field_movement_layer.world_buffer),
        (World, max_dribble_layer.world_buffer),
        (RobotStatus, world_layer.robot_status_buffer),
        (Referee, world_layer.referee_buffer),
        (ObstacleList, obstacle_layer.obstacles_list_buffer),
        (PrimitiveSet, world_layer.primitive_set_buffer),
        (PrimitiveSet, path_layer.primitive_set_buffer),
        (PathVisualization, path_layer.path_visualization_buffer),
        (PassVisualization, passing_layer.pass_visualization_buffer),
        (AttackerVisualization, attacker_layer.attacker_vis_buffer),
        (World, tactic_layer.world_buffer),
        (PlayInfo, tactic_layer.play_info_buffer),
        (ValidationProtoSet, validation_layer.validation_set_buffer),
        (SimulationState, simulation_control_toolbar.simulation_state_buffer),
        (CostVisualization, cost_vis_layer.cost_visualization_buffer),
        (World, trail_layer.world_buffer),
        (DebugShapes, debug_shapes_layer.debug_shapes_buffer),
        (Referee, referee_layer.referee_vis_buffer),
        (BallPlacementVisualization, referee_layer.ball_placement_vis_buffer),
        (World, referee_layer.world_buffer),
    ]:
        full_system_proto_unix_io.register_observer(*arg)

    return gl_widget


def setup_parameter_widget(
    proto_unix_io: ProtoUnixIO, friendly_colour_yellow: bool
) -> ProtoConfigurationWidget:
    """Setup the parameter widget

    :param proto_unix_io: The proto unix io object
    :param friendly_colour_yellow: Whether the parameter widget is editing the
                                   yellow (true) or blue (false) team's configuration
    :return: The proto configuration (parameter) widget
    """

    def on_change_callback(
        attr: Any, value: Any, updated_proto: ThunderbotsConfig
    ) -> None:
        proto_unix_io.send_proto(ThunderbotsConfig, updated_proto)
        proto_unix_io.send_proto(
            NetworkConfig, updated_proto.ai_config.ai_control_config.network_config
        )

    return ProtoConfigurationWidget(
        on_change_callback, is_yellow=friendly_colour_yellow
    )


def setup_log_widget(proto_unix_io: ProtoUnixIO) -> g3logWidget:
    """Setup the wiget that receives logs from full system

    :param proto_unix_io: The proto unix io object
    :return: The log widget
    """
    # Create widget
    logs = g3logWidget()

    # Register observer
    proto_unix_io.register_observer(RobotLog, logs.log_buffer)

    return logs


def setup_performance_plot(proto_unix_io: ProtoUnixIO) -> ProtoPlotter:
    """Setup the performance plot

    :param proto_unix_io: The proto unix io object
    :return: The performance plot widget
    """

    def extract_namedvalue_data(named_value_data):
        return {named_value_data.name: named_value_data.value}

    # Performance Plots plot HZ so the values can't be negative
    proto_plotter = ProtoPlotter(
        min_y=0,
        max_y=100,
        window_secs=15,
        configuration={NamedValue: extract_namedvalue_data},
    )

    # Register observer
    proto_unix_io.register_observer(NamedValue, proto_plotter.buffers[NamedValue])
    return proto_plotter


def setup_play_info(proto_unix_io: ProtoUnixIO) -> PlayInfoWidget:
    """Setup the play info widget

    :param proto_unix_io: The proto unix io object
    :return: The play info widget
    """
    play_info = PlayInfoWidget()
    proto_unix_io.register_observer(PlayInfo, play_info.playinfo_buffer)
    return play_info


def setup_fps_widget(
    frame_swap_counter: FrameTimeCounter, refresh_counter: FrameTimeCounter
) -> FPSWidget:
    """Setup fps widget

    :param frame_swap_counter: a FrameTimeCounter for the GLWidget to track
                               the time between frame swaps
    :param refresh_counter: a FrameTimeCounter for the refresh function
    :return: the FPS Widget
    """
    return FPSWidget(frame_swap_counter, refresh_counter)


def setup_referee_info(proto_unix_io: ProtoUnixIO) -> RefereeInfoWidget:
    """Setup the referee info widget

    :param proto_unix_io: The proto unix io object
    :return: The referee info widget
    """
    referee_info = RefereeInfoWidget()
    proto_unix_io.register_observer(Referee, referee_info.referee_buffer)
    return referee_info


#################################
#  DIAGNOSTICS RELATED WIDGETS  #
#################################


def setup_robot_view(
    proto_unix_io: ProtoUnixIO, available_control_modes: list[IndividualRobotMode]
) -> RobotView:
    """Setup the robot view widget

    :param proto_unix_io: The proto unix io object for the full system
    :param available_control_modes: The currently available input modes for the robots
                                    according to what mode thunderscope is run in

    :return: The robot view widget
    """
    robot_view = RobotView(available_control_modes)
    proto_unix_io.register_observer(RobotStatus, robot_view.robot_status_buffer)
    proto_unix_io.register_observer(RobotStatistic, robot_view.robot_statistic_buffer)
    return robot_view


def setup_robot_error_log_view_widget(proto_unix_io: ProtoUnixIO) -> RobotErrorLog:
    """Setup the robot error log widget and connect its buffer to the proto unix io

    :param proto_unix_io: The proto unix io object for the full system
    :return: The robot error log widget
    """
    robot_error_log = RobotErrorLog()
    proto_unix_io.register_observer(RobotStatus, robot_error_log.robot_status_buffer)
    proto_unix_io.register_observer(RobotCrash, robot_error_log.robot_crash_buffer)
    proto_unix_io.register_observer(RobotLog, robot_error_log.robot_log_buffer)
    return robot_error_log


def setup_estop_view(proto_unix_io: ProtoUnixIO) -> EstopView:
    """Setup the estop view widget

    :param proto_unix_io: The proto unix io object for the full system
    :return: The estop widget
    """
    estop_view = EstopView()
    proto_unix_io.register_observer(EstopState, estop_view.estop_state_buffer)
    return estop_view


def setup_diagnostics_widget(proto_unix_io: ProtoUnixIO) -> DiagnosticsWidget:
    """Set up the diagnostics widget that provides an interface for manually
    controlling our robots

    :param proto_unix_io: ProtoUnixIO for sending messages to the robot
    :returns: the diagnostics widget
    """
    diagnostics_widget = DiagnosticsWidget(proto_unix_io)
    return diagnostics_widget
