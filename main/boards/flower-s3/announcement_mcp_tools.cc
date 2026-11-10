#include "announcement_mcp_tools.h"

#include "cjson_utils.h"
#include "mcp_server.h"

#include <cstdio>
#include <optional>

namespace flower {
namespace {
ToolResult Status(const GreetingTimeSettings& settings) {
    CJsonUniquePtr result(cJSON_CreateObject());
    if (!result ||
        !cJSON_AddBoolToObject(result.get(), "enabled", settings.AnnouncementsEnabled())) {
        return std::unexpected("Cannot allocate announcement status");
    }
    return ReturnValue(result.release());
}
std::string FormatTime(int minutes) {
    char text[6];
    std::snprintf(text, sizeof(text), "%02d:%02d", minutes / 60, minutes % 60);
    return text;
}

std::optional<int> ParseTime(const std::string& text) {
    if (text.size() != 5 || text[2] != ':')
        return std::nullopt;
    for (const int index : {0, 1, 3, 4}) {
        if (text[index] < '0' || text[index] > '9')
            return std::nullopt;
    }
    const int hour = (text[0] - '0') * 10 + text[1] - '0';
    const int minute = (text[3] - '0') * 10 + text[4] - '0';
    if (hour > 23 || minute > 59)
        return std::nullopt;
    return hour * 60 + minute;
}

ToolResult TimeStatus(const GreetingTimeSettings& settings) {
    const auto schedule = settings.GetSchedule();
    CJsonUniquePtr result(cJSON_CreateObject());
    if (!result ||
        !cJSON_AddStringToObject(result.get(), "work_morning",
                                 FormatTime(schedule.workday.morning).c_str()) ||
        !cJSON_AddStringToObject(result.get(), "work_night",
                                 FormatTime(schedule.workday.night).c_str()) ||
        !cJSON_AddStringToObject(result.get(), "rest_morning",
                                 FormatTime(schedule.restday.morning).c_str()) ||
        !cJSON_AddStringToObject(result.get(), "rest_night",
                                 FormatTime(schedule.restday.night).c_str())) {
        return std::unexpected("Cannot allocate greeting time status");
    }
    return ReturnValue(result.release());
}
}  // namespace

void InitializeAnnouncementTools(GreetingTimeSettings& settings) {
    auto& server = McpServer::GetInstance();
    server.AddTool("self.flower.get_announcements",
                   "查询自动播报总开关，包含主动闲聊、整点报时、早安和晚安。", PropertyList(),
                   [&settings](const PropertyList&) -> ToolResult { return Status(settings); });
    server.AddTool(
        "self.flower.set_announcements_enabled",
        "设置自动播报总开关，同时控制主动闲聊、整点报时、早安和晚安。"
        "用户说“打开报时”“开启报时”“打开闹钟”“打开主动闲聊”“打开闲聊”“开启闲聊”“打开早晚安”时，enab"
        "led=true；"
        "说“关闭报时”“关闭闹钟”“关闭主动闲聊”“关闭闲聊”“关闭早晚安”时，enabled=false。"
        "保存后重启保留。开启后按时间表播报，主动闲聊等待随机间隔。"
        "这不是新增指定时刻的闹钟，不影响手动定型文、对话或既有时间设置。",
        PropertyList({Property("enabled", kPropertyTypeBoolean)}),
        [&settings](const PropertyList& properties) -> ToolResult {
            if (!settings.SaveAnnouncementsEnabled(properties["enabled"].value<bool>())) {
                return std::unexpected(
                    "Failed to save announcement switch; previous setting remains active");
            }
            return Status(settings);
        });
    server.AddTool("self.flower.get_greeting_times",
                   "查询工作日（周一至周五）和双休（周六、周日）的早安、晚安时间。返回 "
                   "HH:MM，使用设备本地时间。",
                   PropertyList(),
                   [&settings](const PropertyList&) -> ToolResult { return TimeStatus(settings); });
    server.AddTool(
        "self.flower.set_greeting_times",
        "设置早安和晚安时间，morning、night 必须为 24 小时制 HH:MM。"
        "scope=all 表示每天相同（默认），workday 表示仅周一至周五，restday 表示仅周六、周日。"
        "例如每天早上八点和晚上八点：morning=08:00，night=20:00，scope=all。"
        "只修改一个时间时，先查询并保留同一时段的另一时间。保存后立即生效，重启保留，不补播。"
        "早晚安相同表示该时段关闭免打扰及早晚安。不会打开或关闭自动播报总开关。",
        PropertyList({Property("morning", kPropertyTypeString).SetMaxLength(5),
                      Property("night", kPropertyTypeString).SetMaxLength(5),
                      Property("scope", kPropertyTypeString, "all").SetMaxLength(7)}),
        [&settings](const PropertyList& properties) -> ToolResult {
            const auto morning = ParseTime(properties["morning"].value<std::string>());
            const auto night = ParseTime(properties["night"].value<std::string>());
            const auto& scope = properties["scope"].value<std::string>();
            if (!morning || !night ||
                (scope != "all" && scope != "workday" && scope != "restday")) {
                return std::unexpected(
                    "Use HH:MM from 00:00 to 23:59 and scope all, workday or restday");
            }
            auto schedule = settings.GetSchedule();
            if (scope != "restday")
                schedule.workday = {*morning, *night};
            if (scope != "workday")
                schedule.restday = {*morning, *night};
            if (!settings.SaveSchedule(schedule)) {
                return std::unexpected(
                    "Failed to save greeting times; previous times remain active");
            }
            return TimeStatus(settings);
        });
}
}  // namespace flower
