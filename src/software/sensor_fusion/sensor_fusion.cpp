#include "software/sensor_fusion/sensor_fusion.h"

#include "software/geom/algorithms/distance.h"
#include "software/logger/logger.h"

SensorFusion::SensorFusion(TbotsProto::SensorFusionConfig sensor_fusion_config)
    : sensor_fusion_config(sensor_fusion_config),
      field(std::nullopt),
      ball(std::nullopt),
      friendly_team(),
      enemy_team(),
      game_state(),
      referee_stage(std::nullopt),
      dribble_displacement(std::nullopt),
      ball_filter(),
      friendly_team_filter(),
      enemy_team_filter(),
      possession(TeamPossession::FRIENDLY_TEAM),
      possession_tracker(std::make_shared<PossessionTracker>(
          sensor_fusion_config.possession_tracker_config())),
      friendly_goalie_id(0),
      enemy_goalie_id(0),
      defending_positive_side(false),
      ball_in_dribbler_timeout(0),
      reset_time_vision_packets_detected(0),
      last_t_capture(0)
{
}

std::optional<World> SensorFusion::getWorld() const
{
    if (field && ball)
    {
        World new_world(*field, *ball, friendly_team, enemy_team);
        new_world.updateGameState(game_state);
        new_world.setTeamWithPossession(possession);
        new_world.setDribbleDisplacement(dribble_displacement);
        if (referee_stage)
        {
            new_world.updateRefereeStage(*referee_stage);
        }

        new_world.setVirtualObstacles(virtual_obstacles_);
        return new_world;
    }
    else
    {
        return std::nullopt;
    }
}

void SensorFusion::processSensorProto(const SensorProto &sensor_msg)
{
    if (sensor_msg.has_ssl_vision_msg())
    {
        updateWorld(sensor_msg.ssl_vision_msg());
    }

    if (sensor_msg.has_ssl_referee_msg())
    {
        updateWorld(sensor_msg.ssl_referee_msg());
    }

    updateWorld(sensor_msg.robot_status_msgs());

    friendly_team.assignGoalie(friendly_goalie_id);
    enemy_team.assignGoalie(enemy_goalie_id);

    if (sensor_fusion_config.override_game_controller_friendly_goalie_id())
    {
        RobotId friendly_goalie_id_override = sensor_fusion_config.friendly_goalie_id();
        friendly_team.assignGoalie(friendly_goalie_id_override);
    }

    if (sensor_fusion_config.override_game_controller_enemy_goalie_id())
    {
        RobotId enemy_goalie_id_override = sensor_fusion_config.enemy_goalie_id();
        enemy_team.assignGoalie(enemy_goalie_id_override);
    }
}


void SensorFusion::updateWorld(const SSLProto::SSL_WrapperPacket &packet)
{
    if (packet.has_geometry())
    {
        updateWorld(packet.geometry());
    }

    if (packet.has_detection())
    {
        if (checkForVisionReset(packet.detection().t_capture()))
        {
            LOG(WARNING) << "Vision reset detected... Resetting SensorFusion!";
            resetWorldComponents();

            // Process the geometry again
            updateWorld(packet.geometry());
        }

        updateWorld(packet.detection());

        if (!ball && (packet.detection().robots_blue().size() != 0 ||
                      packet.detection().robots_yellow().size() != 0))
        {
            LOG(WARNING)
                << "There are robots on the field, but no ball. It is highly likely that sensor fusion has filtered the ball out!";
        }
    }
}

void SensorFusion::updateWorld(const SSLProto::SSL_GeometryData &geometry_packet)
{
    field = createField(geometry_packet);
    if (!field)
    {
        LOG(WARNING)
            << "Invalid field packet has been detected, which means field may be unreliable "
            << "and the createFieldFromPacketGeometry may be parsing using the wrong proto format";
    }
}

void SensorFusion::updateWorld(const SSLProto::Referee &packet)
{
    if (sensor_fusion_config.friendly_color_yellow())
    {
        if (!ssl_referee::deprecated_commands.contains(packet.command()))
            game_state.updateRefereeCommand(
                ssl_referee::createRefereeCommand(packet, TeamColour::YELLOW));
        friendly_goalie_id = packet.yellow().goalkeeper();
        enemy_goalie_id    = packet.blue().goalkeeper();
        if (packet.has_blue_team_on_positive_half())
        {
            defending_positive_side = !packet.blue_team_on_positive_half();
        }
    }
    else
    {
        if (!ssl_referee::deprecated_commands.contains(packet.command()))
            game_state.updateRefereeCommand(
                ssl_referee::createRefereeCommand(packet, TeamColour::BLUE));
        friendly_goalie_id = packet.blue().goalkeeper();
        enemy_goalie_id    = packet.yellow().goalkeeper();
        if (packet.has_blue_team_on_positive_half())
        {
            defending_positive_side = packet.blue_team_on_positive_half();
        }
    }

    if (game_state.isBallPlacement())
    {
        auto pt = getBallPlacementPoint(packet);
        if (pt)
        {
            game_state.setBallPlacementPoint(*pt);
        }
        else
        {
            std::string state = game_state.isOurBallPlacement() ? "BALL_PLACEMENT_US"
                                                                : "BALL_PLACEMENT_THEM";
            LOG(WARNING) << "In " << state << " state, but no ball placement point found"
                         << std::endl;
        }
    }

    referee_stage = ssl_referee::createRefereeStage(packet);
}

void SensorFusion::updateWorld(
    const google::protobuf::RepeatedPtrField<TbotsProto::RobotStatus> &robot_status_msgs)
{
    for (auto &robot_status_msg : robot_status_msgs)
    {
        RobotId robot_id = robot_status_msg.robot_id();
        std::set<RobotCapability> unavailableCapabilities;

        for (const auto &error_code_msg : robot_status_msg.error_code())
        {
            if (error_code_msg == TbotsProto::ErrorCode::HIGH_CAP)
            {
                unavailableCapabilities.insert(RobotCapability::Kick);
                unavailableCapabilities.insert(RobotCapability::Chip);
            }
            else if (error_code_msg == TbotsProto::ErrorCode::DRIBBLER_MOTOR_HOT)
            {
                unavailableCapabilities.insert(RobotCapability::Dribble);
            }
        }
        friendly_team.setUnavailableRobotCapabilities(robot_id, unavailableCapabilities);

        if (robot_status_msg.has_power_status() &&
            robot_status_msg.power_status().breakbeam_tripped())
        {
            friendly_robot_id_with_ball_in_dribbler = robot_id;
            ball_in_dribbler_timeout =
                sensor_fusion_config.num_dropped_detections_before_ball_not_in_dribbler();
        }
    }
}

bool SensorFusion::shouldTrustRobotStatus()
{
    // Check if there is a robot with a tripped breakbeam
    if (!friendly_robot_id_with_ball_in_dribbler.has_value())
    {
        return false;
    }

    std::optional<Robot> robot_with_ball_in_dribbler =
        friendly_team.getRobotById(friendly_robot_id_with_ball_in_dribbler.value());
    if (!robot_with_ball_in_dribbler.has_value())
    {
        return false;
    }

    // Check if vision detects a ball on the field
    if (!ball.has_value())
    {
        return true;
    }

    // In other words, we trust the breakbeam reading from robot status if vision also
    // agrees that the ball is roughly near the robot or if ssl vision doesn't detect an
    // ball. If vision has the ball far from the breakbeam detection, then we will ignore
    // the breakbeam detection and trust vision instead.
    return distance(robot_with_ball_in_dribbler->position(), ball->position()) <=
           DISTANCE_THRESHOLD_FOR_BREAKBEAM_FAULT_DETECTION;
}



void SensorFusion::updateWorld(const SSLProto::SSL_DetectionFrame &ssl_detection_frame)
{
    double min_valid_x              = sensor_fusion_config.min_valid_x();
    double max_valid_x              = sensor_fusion_config.max_valid_x();
    bool ignore_invalid_camera_data = sensor_fusion_config.ignore_invalid_camera_data();
    bool friendly_team_is_yellow    = sensor_fusion_config.friendly_color_yellow();

    std::optional<Ball> new_ball;
    auto ball_detections = createBallDetections({ssl_detection_frame}, min_valid_x,
                                                max_valid_x, ignore_invalid_camera_data);

    auto yellow_team =
        createTeamDetection({ssl_detection_frame}, TeamColour::YELLOW, min_valid_x,
                            max_valid_x, ignore_invalid_camera_data);
    auto blue_team =
        createTeamDetection({ssl_detection_frame}, TeamColour::BLUE, min_valid_x,
                            max_valid_x, ignore_invalid_camera_data);

    if (defending_positive_side)
    {
        for (auto &detection : ball_detections)
        {
            detection = invert(detection);
        }
        for (auto &detection : yellow_team)
        {
            detection = invert(detection);
        }
        for (auto &detection : blue_team)
        {
            detection = invert(detection);
        }
    }

    if (friendly_team_is_yellow)
    {
        friendly_team = createFriendlyTeam(yellow_team);
        enemy_team    = createEnemyTeam(blue_team);
    }
    else
    {
        friendly_team = createFriendlyTeam(blue_team);
        enemy_team    = createEnemyTeam(yellow_team);
    }

    ball_in_dribbler_timeout--;
    if (ball_in_dribbler_timeout <= 0)
    {
        friendly_robot_id_with_ball_in_dribbler = std::nullopt;
        ball_in_dribbler_timeout                = 0;
    }

    if (shouldTrustRobotStatus())
    {
        // friendly_robot_id_with_ball_in_dribbler will always have a value since this is
        // checked by the member function shouldTrustRobotStatus
        std::optional<Robot> robot_with_ball_in_dribbler =
            friendly_team.getRobotById(friendly_robot_id_with_ball_in_dribbler.value());

        std::vector<BallDetection> dribbler_in_ball_detection = {BallDetection{
            .position =
                robot_with_ball_in_dribbler->position() +
                Vector::createFromAngle(robot_with_ball_in_dribbler->orientation())
                    .normalize(DIST_TO_FRONT_OF_ROBOT_METERS +
                               BALL_TO_FRONT_OF_ROBOT_DISTANCE_WHEN_DRIBBLING),
            .distance_from_ground = 0,
            .timestamp  = Timestamp::fromSeconds(ssl_detection_frame.t_capture()),
            .confidence = 1}};

        std::optional<Ball> new_ball = createBall(dribbler_in_ball_detection);

        if (new_ball)
        {
            updateBall(*new_ball);
        }
    }
    else
    {
        std::optional<Ball> new_ball = createBall(ball_detections);
        if (new_ball)
        {
            // If vision detected a new ball, then use that one
            updateBall(*new_ball);
        }
        else if (ball)
        {
            // If we already have a ball from a previous frame, but is occluded this frame
            std::optional<Robot> closest_enemy =
                enemy_team.getNearestRobot(ball->position());

            if (closest_enemy.has_value())
            {
                ball = Ball(closest_enemy->position() +
                                Vector::createFromAngle(closest_enemy->orientation())
                                    .normalize(DIST_TO_FRONT_OF_ROBOT_METERS),
                            Vector(0, 0), closest_enemy->timestamp());
            }
        }

        // we shouldn't trust breakbeam so we reset the dribbler and its associated
        // variables
        friendly_robot_id_with_ball_in_dribbler = std::nullopt;
        ball_in_dribbler_timeout                = 0;
    }

    if (ball && field)
    {
        possession = possession_tracker->getTeamWithPossession(friendly_team, enemy_team,
                                                               *ball, *field);
        updateDribbleDisplacement();
    }
}

void SensorFusion::updateBall(Ball new_ball)
{
    ball = new_ball;
    game_state.updateBall(*ball);
}

std::optional<Ball> SensorFusion::createBall(
    const std::vector<BallDetection> &ball_detections)
{
    if (field)
    {
        std::optional<Ball> new_ball =
            ball_filter.estimateBallState(ball_detections, field.value().fieldBoundary());
        return new_ball;
    }
    return std::nullopt;
}

Team SensorFusion::createFriendlyTeam(const std::vector<RobotDetection> &robot_detections)
{
    Team new_friendly_team = friendly_team_filter.getFilteredData(
        friendly_team, robot_detections, friendly_robot_id_with_ball_in_dribbler);
    return new_friendly_team;
}

void SensorFusion::updateDribbleDisplacement()
{
    // Dribble distance algorithm taken from TIGERs autoref implementation
    // https://t.ly/vNZf9

    if (!ball.has_value())
    {
        return;
    }

    // Add new touching robots and remove non-touching robots
    for (const Robot &robot : friendly_team.getAllRobots())
    {
        if (robot.isNearDribbler(ball->position(),
                                 sensor_fusion_config.touching_ball_threshold_meters()))
        {
            // Insert only occurs if the map doesn't already contain a value
            // with the key robot.id()
            ball_contacts_by_friendly_robots.insert(
                std::make_pair(robot.id(), ball->position()));
        }
        else
        {
            ball_contacts_by_friendly_robots.erase(robot.id());
        }
    }
    // Remove touching robots that have vanished
    for (const auto &[robot_id, contact_point] : ball_contacts_by_friendly_robots)
    {
        if (std::none_of(friendly_team.getAllRobots().begin(),
                         friendly_team.getAllRobots().end(),
                         [&](const Robot &robot) { return robot.id() == robot_id; }))
        {
            ball_contacts_by_friendly_robots.erase(robot_id);
        }
    }
    // Compute displacements from initial contact points to current ball position
    std::vector<Segment> dribble_displacements;
    dribble_displacements.reserve(ball_contacts_by_friendly_robots.size());

    std::transform(ball_contacts_by_friendly_robots.begin(),
                   ball_contacts_by_friendly_robots.end(),
                   std::back_inserter(dribble_displacements),
                   [&](const auto &kv_pair)
                   {
                       const Point contact_point = kv_pair.second;
                       return Segment(contact_point, ball->position());
                   });

    // Set dribble_displacement to the longest of dribble_displacements
    if (dribble_displacements.empty())
    {
        dribble_displacement = std::nullopt;
    }
    else
    {
        dribble_displacement = *std::max_element(
            dribble_displacements.begin(), dribble_displacements.end(),
            [](const Segment &a, const Segment &b) { return a.length() < b.length(); });
    }
}

Team SensorFusion::createEnemyTeam(const std::vector<RobotDetection> &robot_detections)
{
    Team new_enemy_team =
        enemy_team_filter.getFilteredData(enemy_team, robot_detections, false);
    return new_enemy_team;
}

std::optional<Point> SensorFusion::getBallPlacementPoint(const SSLProto::Referee &packet)
{
    std::optional<Point> point_opt = ssl_referee::getBallPlacementPoint(packet);

    if (!point_opt)
    {
        return point_opt;
    }

    // if we're defending the positive side, then in our reference frame, we will have
    // everything flipped
    if (defending_positive_side)
    {
        return Point(-point_opt.value().x(), -point_opt.value().y());
    }

    return point_opt;
}

RobotDetection SensorFusion::invert(RobotDetection robot_detection) const
{
    robot_detection.position =
        Point(-robot_detection.position.x(), -robot_detection.position.y());
    robot_detection.orientation = robot_detection.orientation + Angle::half();
    return robot_detection;
}

BallDetection SensorFusion::invert(BallDetection ball_detection) const
{
    ball_detection.position =
        Point(-ball_detection.position.x(), -ball_detection.position.y());
    return ball_detection;
}

bool SensorFusion::teamHasBall(const Team &team, const Ball &ball)
{
    for (const auto &robot : team.getAllRobots())
    {
        if (robot.isNearDribbler(ball.position()))
        {
            return true;
        }
    }
    return false;
}

bool SensorFusion::checkForVisionReset(double t_capture)
{
    if (t_capture < last_t_capture && t_capture < VISION_PACKET_RESET_TIME_THRESHOLD)
    {
        reset_time_vision_packets_detected++;
    }
    else
    {
        reset_time_vision_packets_detected = 0;
        last_t_capture                     = t_capture;
    }

    if (reset_time_vision_packets_detected > VISION_PACKET_RESET_COUNT_THRESHOLD)
    {
        last_t_capture                     = 0;
        reset_time_vision_packets_detected = 0;
        return true;
    }

    return false;
}

void SensorFusion::resetWorldComponents()
{
    field                = std::nullopt;
    ball                 = std::nullopt;
    friendly_team        = Team();
    enemy_team           = Team();
    game_state           = GameState();
    referee_stage        = std::nullopt;
    ball_filter          = BallFilter();
    friendly_team_filter = RobotTeamFilter();
    enemy_team_filter    = RobotTeamFilter();
    possession           = TeamPossession::FRIENDLY_TEAM;
    dribble_displacement = std::nullopt;
}

void SensorFusion::setVirtualObstacles(TbotsProto::VirtualObstacles virtual_obstacles)
{
    virtual_obstacles_ = virtual_obstacles;
}
