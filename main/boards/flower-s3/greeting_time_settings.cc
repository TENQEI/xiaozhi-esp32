#include "greeting_time_settings.h"

#include <esp_log.h>
#include <nvs.h>

namespace flower {
namespace {
constexpr char kNamespace[] = "flower_time";
constexpr char kKey[] = "schedule_v3";
constexpr char kLegacyScheduleKey[] = "schedule_v2";
constexpr char kLegacyKey[] = "times_v1";
constexpr char kAnnouncementsKey[] = "announce_on";
constexpr char kTag[] = "FlowerTime";
}  // namespace

GreetingTimeSettings::GreetingTimeSettings() {
    nvs_handle_t handle;
    if (nvs_open(kNamespace, NVS_READONLY, &handle) != ESP_OK) {
        return;
    }
    uint32_t enabled;
    if (nvs_get_u32(handle, kAnnouncementsKey, &enabled) == ESP_OK && enabled <= 1) {
        announcements_enabled_ = enabled != 0;
    }
    uint32_t stored[2] = {};
    size_t size = sizeof(stored);
    const auto error = nvs_get_blob(handle, kKey, stored, &size);
    GreetingSchedule decoded{UnpackTimes(stored[0]), UnpackTimes(stored[1])};
    if (error == ESP_OK && size == sizeof(stored) && ValidSchedule(decoded)) {
        schedule_ = decoded;
        overridden_ = true;
    } else {
        uint32_t legacy[3] = {};
        size_t legacy_size = sizeof(legacy);
        uint32_t packed;
        if (nvs_get_blob(handle, kLegacyScheduleKey, legacy, &legacy_size) == ESP_OK &&
            legacy_size == sizeof(legacy) && legacy[0] <= 2 && ValidTimes(UnpackTimes(legacy[1])) &&
            ValidTimes(UnpackTimes(legacy[2]))) {
            // Former daily mode used only the first pair. The two-pair modes
            // keep both pairs and now follow ordinary Mon-Fri/weekends.
            schedule_ = {UnpackTimes(legacy[1]),
                         UnpackTimes(legacy[0] == 0 ? legacy[1] : legacy[2])};
            overridden_ = true;
        } else if (nvs_get_u32(handle, kLegacyKey, &packed) == ESP_OK &&
                   ValidTimes(UnpackTimes(packed))) {
            // Preserve one-pair settings on old devices, without writes at boot.
            schedule_ = {UnpackTimes(packed), UnpackTimes(packed)};
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
            schedule_ = {times, times};
        }
    }
}

bool GreetingTimeSettings::Save(GreetingTimes times) { return SaveSchedule({times, times}); }

bool GreetingTimeSettings::AnnouncementsEnabled() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return announcements_enabled_;
}

bool GreetingTimeSettings::SaveAnnouncementsEnabled(bool enabled) {
    // Serialize MCP/HTTP writes so the published value follows committed order.
    std::lock_guard<std::mutex> writer(announcement_write_mutex_);
    if (AnnouncementsEnabled() == enabled) {
        return true;
    }
    nvs_handle_t handle;
    esp_err_t error = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (error != ESP_OK) {
        return false;
    }
    error = nvs_set_u32(handle, kAnnouncementsKey, enabled ? 1 : 0);
    if (error == ESP_OK) {
        error = nvs_commit(handle);
    }
    nvs_close(handle);
    if (error != ESP_OK) {
        ESP_LOGW(kTag, "Cannot save announcement switch: %s", esp_err_to_name(error));
        return false;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    announcements_enabled_ = enabled;
    return true;
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
    const uint32_t stored[] = {PackTimes(schedule.workday), PackTimes(schedule.restday)};
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
    ESP_LOGI(kTag, "Saved weekday and weekend greeting times");
    return true;
}

}  // namespace flower
