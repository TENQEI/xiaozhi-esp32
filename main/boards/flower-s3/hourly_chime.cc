#include "hourly_chime.h"
#include "application.h"
#include "random_phrase.h"

#include <esp_random.h>
#include <esp_timer.h>

namespace flower {

void HourlyChime::Tick(bool suppressed) {
    auto& app = Application::GetInstance();
    const auto now = std::time(nullptr);
    const auto greetings = GreetingsForDate(times_.GetSchedule(), now);
    config_ = {12,
               audio_.AutomaticEnabled() && times_.AnnouncementsEnabled(),
               greetings,
               audio_.GreetingEnabled(true),
               audio_.GreetingEnabled(false)};
    const bool idle = !suppressed && app.GetDeviceState() == kDeviceStateIdle;
    const int index = schedule_.Poll(now, config_, idle);
    if (index >= 0) {
        audio_.PlayClock(index);
    } else if (index == ChimeSchedule::kGoodMorning || index == ChimeSchedule::kGoodNight) {
        audio_.PlayGreeting(index == ChimeSchedule::kGoodMorning);
    }

    const int second = static_cast<int>(now % 86400);
    if (!config_.enabled || PhraseHour(now) < 0 || !idle || index != -1 ||
        !app.GetAudioService().IsPlaybackIdle() ||
        greetings.IsQuiet(second / 60)) {
        ResetPhraseTimer();
        return;
    }

    const int64_t monotonic_us = esp_timer_get_time();
    if (next_phrase_us_ == 0) {
        constexpr uint32_t kMinSeconds = 30 * 60;
        constexpr uint32_t kMaxSeconds = 90 * 60;
        const auto seconds = kMinSeconds + esp_random() % (kMaxSeconds - kMinSeconds + 1);
        next_phrase_us_ = monotonic_us + static_cast<int64_t>(seconds) * 1000000;
    } else if (monotonic_us >= next_phrase_us_) {
        ResetPhraseTimer();
        // Allow a full local clip to finish before the next scheduled announcement.
        constexpr int kGuardSeconds = 62;
        const int night = greetings.NightMinute();
        if (3600 - second % 3600 > kGuardSeconds &&
            (night < 0 || (night * 60 - second + 86400) % 86400 > kGuardSeconds)) {
            audio_.PlayPhrase();
        }
    }
}

}  // namespace flower
