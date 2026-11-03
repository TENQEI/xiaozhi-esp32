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
    if (!cJSON_IsNumber(version) || (version->valuedouble != 1 && version->valuedouble != 2) ||
        !cJSON_IsNumber(count) || count->valuedouble != count->valueint || count->valueint < 0 ||
        count->valueint > 64) {
        ESP_LOGW(kTag, "Invalid random phrase manifest");
        return;
    }
    PhraseCounts counts{};
    if (version->valueint == 1) {
        counts[0] = count->valueint;  // Old ungrouped packs are all-day clips.
    } else {
        constexpr const char* names[] = {"common", "morning", "afternoon", "evening"};
        for (size_t i = 0; i < counts.size(); ++i) {
            const auto* item = cJSON_GetObjectItemCaseSensitive(root.get(), names[i]);
            if (!cJSON_IsNumber(item) || item->valuedouble != item->valueint ||
                item->valueint < 0 || item->valueint > 64) {
                ESP_LOGW(kTag, "Invalid phrase group count");
                return;
            }
            counts[i] = item->valueint;
        }
        if (PhraseCount(counts) != count->valueint) {
            ESP_LOGW(kTag, "Phrase group counts do not match total");
            return;
        }
    }
    counts_ = counts;
    ESP_LOGI(kTag, "Random phrases: common=%d, morning=%d, afternoon=%d, evening=%d", counts_[0],
             counts_[1], counts_[2], counts_[3]);
}

void RandomPhrasePlayer::Play() {
    auto& app = Application::GetInstance();
    if (app.GetDeviceState() != kDeviceStateIdle || !app.GetAudioService().IsPlaybackIdle()) {
        return;
    }
    if (!loaded_) {
        LoadConfig();
    }
    const int index =
        RandomPhraseIndexForHour(esp_random(), counts_, PhraseHour(std::time(nullptr)), previous_);
    if (index < 0) {
        ESP_LOGI(kTag, "No eligible recordings for the current time; double click ignored");
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
