#include "announcement_mcp_tools.h"

#include "cjson_utils.h"
#include "mcp_server.h"

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
}
}  // namespace flower
