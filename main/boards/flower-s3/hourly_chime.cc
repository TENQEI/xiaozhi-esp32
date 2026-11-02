#include "hourly_chime.h"

#include "application.h"
#include "assets.h"
#include "cjson_utils.h"

#include <esp_log.h>
#include <cstdio>

namespace flower {
namespace {
constexpr char kTag[] = "FlowerChime";
}

void HourlyChime::LoadConfig() {
    loaded_ = true;
    void* data = nullptr;
    size_t size = 0;
    if (!Assets::GetInstance().GetAssetData("flower_chime.json", data, size) || data == nullptr ||
        size == 0 || size > 1024) {
        ESP_LOGI(kTag, "No chime manifest; automatic chimes disabled");
        return;
    }
    CJsonUniquePtr root(cJSON_ParseWithLength(static_cast<const char*>(data), size));
    if (!root || !cJSON_IsObject(root.get())) {
        ESP_LOGW(kTag, "Invalid chime manifest");
        return;
    }
    auto integer = [&root](const char* name, int minimum, int maximum) -> int {
        const auto* item = cJSON_GetObjectItemCaseSensitive(root.get(), name);
        if (!cJSON_IsNumber(item) || item->valuedouble != item->valueint ||
            item->valueint < minimum || item->valueint > maximum) {
            return -1;
        }
        return item->valueint;
    };
    const int version = integer("version", 1, 1);
    const int count = integer("count", 0, 24);
    const int start = integer("quiet_start", 0, 23);
    const int end = integer("quiet_end", 0, 23);
    const auto* enabled = cJSON_GetObjectItemCaseSensitive(root.get(), "enabled");
    const auto* morning = cJSON_GetObjectItemCaseSensitive(root.get(), "good_morning");
    const auto* night = cJSON_GetObjectItemCaseSensitive(root.get(), "good_night");
    if (version != 1 || (count != 0 && count != 1 && count != 12 && count != 24) || start < 0 ||
        end < 0 || !cJSON_IsBool(enabled) || (morning && !cJSON_IsBool(morning)) ||
        (night && !cJSON_IsBool(night))) {
        ESP_LOGW(kTag, "Unsupported chime configuration");
        return;
    }
    const bool has_morning = cJSON_IsTrue(morning);
    const bool has_night = cJSON_IsTrue(night);
    config_ = {count,       (count > 0 || has_morning || has_night) && cJSON_IsTrue(enabled),
               start,       end,
               has_morning, has_night};
    ESP_LOGI(kTag, "Chimes: %d files, enabled=%d, quiet=%02d:00-%02d:00", count, config_.enabled,
             start, end);
}

bool HourlyChime::Play(int index) {
    if (index < 0 || index >= config_.count) {
        return false;
    }
    char name[32];
    std::snprintf(name, sizeof(name), "flower_chime_%02d.ogg", index);
    const bool started = Application::GetInstance().PlayLocalNotification(name);
    ESP_LOGI(kTag, "%s %s", started ? "Playing" : "Skipped", name);
    return started;
}

void HourlyChime::Tick() {
    auto& app = Application::GetInstance();
    const bool idle = app.GetDeviceState() == kDeviceStateIdle;
    if (!loaded_ && idle) {
        LoadConfig();
    }
    const int index = schedule_.Poll(std::time(nullptr), config_, idle);
    if (index >= 0) {
        Play(index);
    } else if (index == ChimeSchedule::kGoodMorning || index == ChimeSchedule::kGoodNight) {
        const char* name = index == ChimeSchedule::kGoodMorning ? "flower_greeting_morning.ogg"
                                                                : "flower_greeting_night.ogg";
        const bool started = app.PlayLocalNotification(name);
        ESP_LOGI(kTag, "%s %s", started ? "Playing" : "Skipped", name);
    }
}

}  // namespace flower
