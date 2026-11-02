#include "greeting_time_settings.h"

#include <esp_log.h>
#include <nvs.h>

namespace flower {
namespace {
constexpr char kNamespace[] = "flower_time";
constexpr char kKey[] = "times_v1";
constexpr char kTag[] = "FlowerTime";
}  // namespace

GreetingTimeSettings::GreetingTimeSettings() {
    nvs_handle_t handle;
    if (nvs_open(kNamespace, NVS_READONLY, &handle) != ESP_OK) {
        return;
    }
    uint32_t packed;
    if (nvs_get_u32(handle, kKey, &packed) == ESP_OK && ValidTimes(UnpackTimes(packed))) {
        override_.store(packed);
    }
    nvs_close(handle);
}

GreetingTimes GreetingTimeSettings::Get() const {
    const uint32_t packed = override_.load();
    return UnpackTimes(packed == kUnset ? defaults_.load() : packed);
}

void GreetingTimeSettings::SetDefaults(GreetingTimes times) {
    if (ValidTimes(times)) {
        defaults_.store(PackTimes(times));
    }
}

bool GreetingTimeSettings::Save(GreetingTimes times) {
    if (!ValidTimes(times)) {
        return false;
    }
    nvs_handle_t handle;
    esp_err_t error = nvs_open(kNamespace, NVS_READWRITE, &handle);
    if (error != ESP_OK) {
        ESP_LOGW(kTag, "Cannot open time settings: %s", esp_err_to_name(error));
        return false;
    }
    error = nvs_set_u32(handle, kKey, PackTimes(times));
    if (error == ESP_OK) {
        error = nvs_commit(handle);
    }
    nvs_close(handle);
    if (error != ESP_OK) {
        ESP_LOGW(kTag, "Cannot save time settings: %s", esp_err_to_name(error));
        return false;
    }
    override_.store(PackTimes(times));
    ESP_LOGI(kTag, "Saved greeting times: morning=%02d:%02d, night=%02d:%02d", times.morning / 60,
             times.morning % 60, times.night / 60, times.night % 60);
    return true;
}

}  // namespace flower
