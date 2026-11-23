#include "countdown_mcp_tools.h"

#include <esp_timer.h>
#include <charconv>

#include "application.h"
#include "cjson_utils.h"
#include "countdown_timer.h"
#include "mcp_server.h"

namespace flower {
namespace {

ToolResult Reply(const CountdownTimer& timer, int64_t now, const char* result,
                 const std::string& speech, uint32_t token = 0) {
    using State = CountdownTimer::State;
    const auto state = timer.GetState();
    const char* name = state == State::kRunning   ? "running"
                       : state == State::kRinging ? "ringing"
                                                  : "idle";
    CJsonUniquePtr json(cJSON_CreateObject());
    if (!json || !cJSON_AddStringToObject(json.get(), "result", result) ||
        !cJSON_AddStringToObject(json.get(), "state", name) ||
        !cJSON_AddNumberToObject(json.get(), "remaining_seconds", timer.RemainingSeconds(now)) ||
        !cJSON_AddStringToObject(json.get(), "speech", speech.c_str()) ||
        (token &&
         !cJSON_AddStringToObject(json.get(), "confirmation", std::to_string(token).c_str())))
        return std::unexpected("Cannot allocate countdown status");
    return ReturnValue(json.release());
}

std::string SpokenDuration(int seconds) {
    if (seconds == CountdownTimer::kMaxSeconds)
        return "一小时";
    std::string text;
    if (seconds >= 60)
        text = std::to_string(seconds / 60) + "分钟";
    if (seconds % 60)
        text += std::to_string(seconds % 60) + "秒";
    return text;
}

}  // namespace

void InitializeCountdownTools(CountdownTimer& timer) {
    using State = CountdownTimer::State;
    using Action = CountdownTimer::Action;
    auto& server = McpServer::GetInstance();
    server.AddTool(
        "self.flower.timer_start",
        "用户说计时、倒计时或重新计时时调用。把分钟或小时换算成秒，例如 5 分钟传 300。"
        "原样播报 speech。需要二次确认时，播完询问后等待下一轮。"
        "收到确认才把 confirmation 原样传给 "
        "timer_confirm。成功启动的一句确认播完后设备会自动结束对话。",
        PropertyList({Property("seconds", kPropertyTypeInteger, 1, CountdownTimer::kMaxSeconds)}),
        [&timer](const PropertyList& params) -> ToolResult {
            auto& app = Application::GetInstance();
            if (!app.HasOpenConversation())
                return std::unexpected("Open a device conversation to set a timer");
            const auto now = esp_timer_get_time();
            const int seconds = params["seconds"].value<int>();
            if (timer.Start(seconds, now)) {
                app.CloseAfterCurrentReply();
                return Reply(timer, now, "started", "好，计时" + SpokenDuration(seconds) + "。");
            }
            if (timer.GetState() == State::kRunning) {
                const auto token = timer.Request(Action::kReplace, seconds, now);
                return Reply(
                    timer, now, "confirmation_required",
                    "要结束现在的计时，改成" + SpokenDuration(seconds) + "吗？请说确认替换。",
                    token);
            }
            return Reply(timer, now, "ringing", "计时到啦，按一下按钮就能停。");
        });
    server.AddTool(
        "self.flower.timer_status",
        "查询花花的计时状态或剩余时间。用户问还剩多久、有没有设计时时都调用它，并简短播报 speech。",
        PropertyList(), [&timer](const PropertyList&) -> ToolResult {
            const auto now = esp_timer_get_time();
            const auto state = timer.Poll(now);
            return Reply(timer, now, "status",
                         state == State::kRunning
                             ? "还剩" + SpokenDuration(timer.RemainingSeconds(now)) + "。"
                         : state == State::kRinging ? "计时到啦，按一下按钮就能停。"
                                                    : "现在没有计时。");
        });
    server.AddTool("self.flower.timer_cancel",
                   "请求取消正在运行的计时。原样播报 speech 并等待下一轮明确确认。"
                   "收到确认才把 confirmation 原样传给 timer_confirm；用户拒绝时不调用确认工具。",
                   PropertyList(), [&timer](const PropertyList&) -> ToolResult {
                       if (!Application::GetInstance().HasOpenConversation())
                           return std::unexpected("Open a device conversation to cancel a timer");
                       const auto now = esp_timer_get_time();
                       const auto token = timer.Request(Action::kCancel, 0, now);
                       if (token)
                           return Reply(timer, now, "confirmation_required",
                                        "要取消现在的计时吗？请说确认取消。", token);
                       return Reply(timer, now, "status",
                                    timer.GetState() == State::kRinging
                                        ? "计时到啦，按一下按钮就能停。"
                                        : "现在没有计时。");
                   });
    server.AddTool("self.flower.timer_confirm",
                   "只有在花花问过是否取消或替换、且用户在下一轮明确同意时才调用。"
                   "原样传入上次的 confirmation。拒绝、歧义和失败均不得重试确认。"
                   "只播报 speech。替换成功时，播完设备自动结束对话。",
                   PropertyList({Property("confirmation", kPropertyTypeString).SetMaxLength(10)}),
                   [&timer](const PropertyList& params) -> ToolResult {
                       auto& app = Application::GetInstance();
                       const auto now = esp_timer_get_time();
                       const auto& value = params["confirmation"].value<std::string>();
                       uint32_t token = 0;
                       const auto [end, error] =
                           std::from_chars(value.data(), value.data() + value.size(), token);
                       Action action;
                       if (!app.HasOpenConversation() || error != std::errc{} ||
                           end != value.data() + value.size() || !timer.Confirm(token, now, action))
                           return Reply(timer, now, "confirmation_invalid", "这次没有确认成功。");
                       if (action == Action::kReplace) {
                           app.CloseAfterCurrentReply();
                           return Reply(
                               timer, now, "started",
                               "好，计时" + SpokenDuration(timer.RemainingSeconds(now)) + "。");
                       }
                       return Reply(timer, now, "cancelled", "计时已取消。");
                   });
}

}  // namespace flower
