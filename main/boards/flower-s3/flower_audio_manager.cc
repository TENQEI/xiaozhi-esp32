#include "flower_audio_manager.h"

#include "application.h"
#include "flower_audio_assets.h"
#include "random_phrase.h"

#include <esp_random.h>

namespace flower {
namespace sounds = Flower::Sounds;

std::string_view FlowerAudioManager::StartupSound() const {
    return sounds::STARTUP_READY_ENABLED ? sounds::STARTUP_READY : std::string_view{};
}

std::string_view FlowerAudioManager::WifiConfigSound() const {
    return sounds::WIFI_CONFIG_ENABLED ? sounds::WIFI_CONFIG : std::string_view{};
}

bool FlowerAudioManager::AutomaticEnabled() const { return sounds::AUTOMATIC_ENABLED; }

bool FlowerAudioManager::GreetingEnabled(bool morning) const {
    return morning ? sounds::GREETING_MORNING_ENABLED : sounds::GREETING_NIGHT_ENABLED;
}

bool FlowerAudioManager::PlayClock(int index) {
    return index >= 0 && index < static_cast<int>(sounds::CLOCK.size()) &&
           Application::GetInstance().PlayLocalAudio(sounds::CLOCK[index].data);
}

bool FlowerAudioManager::PlayGreeting(bool morning) {
    return GreetingEnabled(morning) &&
           Application::GetInstance().PlayLocalAudio(morning ? sounds::GREETING_MORNING
                                                             : sounds::GREETING_NIGHT);
}

void FlowerAudioManager::PlayPhrase() {
    auto& app = Application::GetInstance();
    if (app.GetDeviceState() != kDeviceStateIdle || !app.GetAudioService().IsPlaybackIdle()) {
        return;
    }
    const PhraseCounts counts{static_cast<int>(sounds::PHRASE_ANYTIME.size()),
                              static_cast<int>(sounds::PHRASE_MORNING.size()),
                              static_cast<int>(sounds::PHRASE_AFTERNOON.size()),
                              static_cast<int>(sounds::PHRASE_EVENING.size())};
    const int index = RandomPhraseIndexForHour(esp_random(), counts, PhraseHour(std::time(nullptr)),
                                               previous_phrase_);
    if (index < 0) {
        return;
    }
    const sounds::Clip* groups[] = {sounds::PHRASE_ANYTIME.data(), sounds::PHRASE_MORNING.data(),
                                    sounds::PHRASE_AFTERNOON.data(), sounds::PHRASE_EVENING.data()};
    int position = index;
    for (size_t group = 0; group < counts.size(); ++group) {
        if (position < counts[group]) {
            if (app.PlayLocalAudio(groups[group][position].data)) {
                previous_phrase_ = index;
            }
            return;
        }
        position -= counts[group];
    }
}

std::string_view FlowerAudioManager::SessionSound(bool starting) {
    const int slot = starting ? 0 : 1;
    const auto* clips = starting ? sounds::SESSION_START.data() : sounds::SESSION_END.data();
    const int count = starting ? sounds::SESSION_START.size() : sounds::SESSION_END.size();
    const int index = RandomPhraseIndex(esp_random(), count, previous_session_[slot]);
    pending_session_[slot] = index;
    return index < 0 ? std::string_view{} : clips[index].data;
}

void FlowerAudioManager::CommitSessionSound(bool starting) {
    const int slot = starting ? 0 : 1;
    previous_session_[slot] = pending_session_[slot];
}

}  // namespace flower
