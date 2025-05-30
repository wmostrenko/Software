#include "software/logger/network_sink.h"

#include "base64.h"
#include "google/protobuf/any.pb.h"
#include "proto/message_translation/tbots_protobuf.h"
#include "proto/robot_log_msg.pb.h"
#include "shared/constants.h"
#include "software/logger/custom_logging_levels.h"
#include "software/networking/tbots_network_exception.h"

NetworkSink::NetworkSink(int robot_id, bool enable_log_merging)
    : robot_id(robot_id), log_merger(LogMerger(enable_log_merging))
{
}

void NetworkSink::replaceUdpSender(
    std::shared_ptr<ThreadedProtoUdpSender<TbotsProto::RobotLog>> new_sender)
{
    std::unique_lock<std::mutex> lock(robot_log_sender_mutex);
    robot_log_sender = new_sender;
}

void NetworkSink::sendToNetwork(g3::LogMessageMover log_entry)
{
    g3::LogMessage new_log = log_entry.get();
    for (const g3::LogMessage& log : log_merger.log(new_log))
    {
        sendOneLogToNetwork(log);
    }
}

void NetworkSink::sendOneLogToNetwork(const g3::LogMessage& log)
{
    std::optional<std::shared_ptr<ThreadedProtoUdpSender<TbotsProto::RobotLog>>>
        log_sender;
    {
        std::unique_lock<std::mutex> lock(robot_log_sender_mutex);
        log_sender = robot_log_sender;
    }
    if (!log_sender)
    {
        return;
    }

    auto log_msg_proto = std::make_unique<TbotsProto::RobotLog>();
    TbotsProto::LogLevel log_level_proto;

    if (TbotsProto::LogLevel_Parse(log.level(), &log_level_proto))
    {
        log_msg_proto->set_log_msg(log.message());
        log_msg_proto->set_robot_id(robot_id);
        log_msg_proto->set_log_level(log_level_proto);
        log_msg_proto->set_file_name(log.file());
        log_msg_proto->set_line_number(static_cast<uint32_t>(std::stoul(log.line())));

        TbotsProto::Timestamp timestamp;
        const auto current_time_ms =
            std::chrono::time_point_cast<std::chrono::milliseconds>(
                std::chrono::system_clock::now());
        timestamp.set_epoch_timestamp_seconds(
            static_cast<double>(current_time_ms.time_since_epoch().count()) /
            MILLISECONDS_PER_SECOND);
        *(log_msg_proto->mutable_created_timestamp()) = timestamp;

        robot_log_sender.value()->sendProto(*log_msg_proto);
    }
}
