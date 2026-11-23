#ifndef FLOWER_POWER_POLICY_H_
#define FLOWER_POWER_POLICY_H_

#include <cstdint>
#include "greeting_schedule.h"

namespace flower {

// Monotonic deadlines: changing the civil clock cannot extend online standby.
class PowerPolicy {
public:
    static constexpr int64_t kOnlineUs = 5LL * 60 * 1000000;
    bool Poll(int64_t now, bool conversation, bool idle) {
        if (conversation) {
            in_conversation_ = true;
            return false;
        }
        if (in_conversation_ || (!initialized_ && idle)) {
            online_until_ = now + kOnlineUs;
            initialized_ = true;
            in_conversation_ = false;
        }
        return initialized_ && idle && now >= online_until_;
    }
    void Expire() {
        initialized_ = true;
        in_conversation_ = false;
        online_until_ = 0;
    }

private:
    bool initialized_ = false;
    bool in_conversation_ = false;
    int64_t online_until_ = 0;
};

// Next useful civil-time boundary, not every quiet-hour tick. A morning boundary
// also resumes the random-phrase timer even when its greeting clip is disabled.
inline std::time_t NextAnnouncementWake(std::time_t now, const GreetingSchedule& settings,
                                        bool enabled, bool morning, bool night) {
    if (!enabled || now < 1704067200)
        return 0;
    const auto minute = now - now % 60;
    for (int i = 1; i <= 8 * 1440; ++i) {
        const auto candidate = minute + i * 60;
        const auto greetings = GreetingsForDate(settings, candidate);
        const int civil_minute = static_cast<int>(candidate / 60 % 1440);
        if (civil_minute == greetings.MorningMinute() ||
            (night && civil_minute == greetings.NightMinute()))
            return candidate;
        if (civil_minute % 60 == 0 && !greetings.IsQuiet(civil_minute))
            return candidate;
    }
    (void)morning;
    return 0;
}
}  // namespace flower
#endif
