#ifndef FLOWER_CHIME_SCHEDULE_H_
#define FLOWER_CHIME_SCHEDULE_H_

#include "greeting_schedule.h"

#include <algorithm>
#include <cstdint>
#include <ctime>

namespace flower {

struct ChimeConfig {
    int count = 0;
    bool enabled = false;
    GreetingDay greetings = {};
    bool good_morning = false;
    bool good_night = false;
};

inline int ChimeIndex(int hour, int count) {
    if (hour < 0 || hour > 23) {
        return -1;
    }
    if (count == 1) {
        return 0;
    }
    if (count == 12) {
        return (hour + 11) % 12;  // 00:00/12:00 use the twelfth recording.
    }
    return count == 24 ? hour : -1;
}

// Pure policy, called from the main task. Timestamp is the upstream clock,
// which OTA already adjusts to local civil time; do not add a timezone again.
class ChimeSchedule {
public:
    static constexpr int kGoodMorning = -2;
    static constexpr int kGoodNight = -3;

    int Poll(std::time_t now, const ChimeConfig& config, bool idle) {
        constexpr std::time_t kValidClock = 1704067200;  // 2024-01-01
        if (now < kValidClock) {
            previous_ = 0;
            return -1;
        }
        const int64_t hour_key = static_cast<int64_t>(now) / 3600;
        const int64_t minute_key = static_cast<int64_t>(now) / 60;
        const auto previous = previous_;
        previous_ = now;
        const bool new_hour = hour_key > latest_hour_;
        const bool new_minute = minute_key > latest_minute_;
        latest_hour_ = std::max(latest_hour_, hour_key);
        latest_minute_ = std::max(latest_minute_, minute_key);
        // Never catch up at boot, after a clock jump, or following a busy hour.
        if (!new_minute || previous == 0 || now <= previous || now - previous > 5 || now % 60 > 5 ||
            !idle || !config.enabled) {
            return -1;
        }
        const int hour = static_cast<int>(hour_key % 24);
        const int minute = static_cast<int>(minute_key % 1440);
        // Boundary greetings take precedence over hourly clips, including the
        // good-night clip at the first instant of the quiet window.
        if (config.good_night && minute == config.greetings.NightMinute()) {
            return kGoodNight;
        }
        if (config.good_morning && minute == config.greetings.MorningMinute()) {
            return kGoodMorning;
        }
        if (!new_hour || now % 3600 > 5 || config.greetings.IsQuiet(minute)) {
            return -1;
        }
        return ChimeIndex(hour, config.count);
    }

private:
    std::time_t previous_ = 0;
    int64_t latest_hour_ = -1;
    int64_t latest_minute_ = -1;
};

}  // namespace flower
#endif  // FLOWER_CHIME_SCHEDULE_H_
