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
                   "查询报时/闹钟总开关。该开关同时控制整点报时、早安和晚安自动播报。",
                   PropertyList(),
                   [&settings](const PropertyList&) -> ToolResult { return Status(settings); });
    server.AddTool(
        "self.flower.set_announcements_enabled",
        "设置报时/闹钟总开关，同时控制整点报时、早安和晚安自动播报。"
        "用户说“打开报时”“开启报时”“打开闹钟”时，enabled=true；"
        "说“关闭报时”“关闭闹钟”时，enabled=false。"
        "立即保存，重启保留；开启不立即播放、不补播。"
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
