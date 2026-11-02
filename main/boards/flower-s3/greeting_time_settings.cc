#include "greeting_time_settings.h"

#include <esp_log.h>
#include <nvs.h>

namespace flower {
namespace {
constexpr char kNamespace[] = "flower_time";
constexpr char kKey[] = "schedule_v2";
constexpr char kLegacyKey[] = "times_v1";
constexpr char kTag[] = "FlowerTime";
}  // namespace

GreetingTimeSettings::GreetingTimeSettings() {
    nvs_handle_t handle;
    if (nvs_open(kNamespace, NVS_READONLY, &handle) != ESP_OK) {
        return;
    }
    uint32_t stored[3] = {};
    size_t size = sizeof(stored);
    const auto error = nvs_get_blob(handle, kKey, stored, &size);
    GreetingSchedule decoded{static_cast<CalendarMode>(stored[0]), UnpackTimes(stored[1]),
                             UnpackTimes(stored[2])};
    if (error == ESP_OK && size == sizeof(stored) && ValidSchedule(decoded)) {
        schedule_ = decoded;
        overridden_ = true;
    } else {
        uint32_t packed;
        if (nvs_get_u32(handle, kLegacyKey, &packed) == ESP_OK && ValidTimes(UnpackTimes(packed))) {
            // Existing devices keep their times and daily behavior. Persist v2
            // on the next explicit save; do not consume flash writes at boot.
            schedule_ = {CalendarMode::Daily, UnpackTimes(packed), UnpackTimes(packed)};
            overridden_ = true;
        }
    }
    nvs_close(handle);
}

GreetingTimes GreetingTimeSettings::Get() const { return GetSchedule().workday; }

GreetingSchedule GreetingTimeSettings::GetSchedule() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return schedule_;
}

void GreetingTimeSettings::SetDefaults(GreetingTimes times) {
    if (ValidTimes(times)) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!overridden_) {
            schedule_ = {CalendarMode::Daily, times, times};
        }
    }
}

bool GreetingTimeSettings::Save(GreetingTimes times) {
    return SaveSchedule({CalendarMode::Daily, times, times});
}

bool GreetingTimeSettings::SaveSchedule(const GreetingSchedule& schedule) {
    if (!ValidSchedule(schedule)) {
        return false;
    }
    nvs_handle_t handle;
    esp_err_t error = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (error != ESP_OK) {
        ESP_LOGW(kTag, "Cannot open time settings: %s", esp_err_to_name(error));
        return false;
    }
    const uint32_t stored[] = {static_cast<uint32_t>(schedule.mode), PackTimes(schedule.workday),
                               PackTimes(schedule.restday)};
    error = nvs_set_blob(handle, kKey, stored, sizeof(stored));
    if (error == ESP_OK) {
        error = nvs_commit(handle);
    }
    nvs_close(handle);
    if (error != ESP_OK) {
        ESP_LOGW(kTag, "Cannot save time settings: %s", esp_err_to_name(error));
        return false;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        schedule_ = schedule;
        overridden_ = true;
    }
    ESP_LOGI(kTag, "Saved greeting schedules, mode=%d", static_cast<int>(schedule.mode));
    return true;
}

}  // namespace flower
