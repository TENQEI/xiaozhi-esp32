#include "random_phrase.h"

#include "application.h"
#include "assets.h"
#include "cjson_utils.h"

#include <esp_log.h>
#include <esp_random.h>
#include <cstdio>

namespace flower {
namespace {
constexpr char kTag[] = "FlowerPhrase";
}

void RandomPhrasePlayer::LoadConfig() {
    loaded_ = true;
    void* data = nullptr;
    size_t size = 0;
    if (!Assets::GetInstance().GetAssetData("flower_random.json", data, size) || data == nullptr ||
        size == 0 || size > 1024) {
        ESP_LOGI(kTag, "No random phrase pack");
        return;
    }
    CJsonUniquePtr root(cJSON_ParseWithLength(static_cast<const char*>(data), size));
    if (!root || !cJSON_IsObject(root.get())) {
        return;
    }
    const auto* version = cJSON_GetObjectItemCaseSensitive(root.get(), "version");
    const auto* count = cJSON_GetObjectItemCaseSensitive(root.get(), "count");
    if (!cJSON_IsNumber(version) || version->valuedouble != 1 || !cJSON_IsNumber(count) ||
        count->valuedouble != count->valueint || count->valueint < 0 || count->valueint > 64) {
        ESP_LOGW(kTag, "Invalid random phrase manifest");
        return;
    }
    count_ = count->valueint;
    ESP_LOGI(kTag, "Random phrases: %d recordings", count_);
}

void RandomPhrasePlayer::Play() {
    auto& app = Application::GetInstance();
    if (app.GetDeviceState() != kDeviceStateIdle || !app.GetAudioService().IsPlaybackIdle()) {
        return;
    }
    if (!loaded_) {
        LoadConfig();
    }
    const int index = RandomPhraseIndex(esp_random(), count_, previous_);
    if (index < 0) {
        ESP_LOGI(kTag, "No random recordings; double click ignored");
        return;
    }
    char name[32];
    std::snprintf(name, sizeof(name), "flower_random_%02d.ogg", index);
    if (app.PlayLocalNotification(name)) {
        previous_ = index;
        ESP_LOGI(kTag, "Playing %s", name);
    }
}

}  // namespace flower
