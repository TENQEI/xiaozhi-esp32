#ifndef FLOWER_CHIME_SCHEDULE_H_
#define FLOWER_CHIME_SCHEDULE_H_

#include <algorithm>
#include <cstdint>
#include <ctime>

namespace flower {

struct ChimeConfig {
    int count = 0;
    bool enabled = false;
    int quiet_start = 20;
    int quiet_end = 4;
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

inline bool IsQuietHour(int hour, int start, int end) {
    if (start == end) {
        return false;
    }
    return start < end ? hour >= start && hour < end : hour >= start || hour < end;
}

// Pure policy, called from the main task. Timestamp is the upstream clock,
// which OTA already adjusts to local civil time; do not add a timezone again.
class ChimeSchedule {
public:
    int Poll(std::time_t now, const ChimeConfig& config, bool idle) {
        constexpr std::time_t kValidClock = 1704067200;  // 2024-01-01
        if (now < kValidClock) {
            previous_ = 0;
            return -1;
        }
        const int64_t hour_key = static_cast<int64_t>(now) / 3600;
        const auto previous = previous_;
        previous_ = now;
        const bool new_hour = hour_key > latest_hour_;
        latest_hour_ = std::max(latest_hour_, hour_key);
        // Never catch up at boot, after a clock jump, or following a busy hour.
        if (!new_hour || previous == 0 || now <= previous || now - previous > 5 || now % 3600 > 5 ||
            !idle || !config.enabled) {
            return -1;
        }
        const int hour = static_cast<int>(hour_key % 24);
        if (IsQuietHour(hour, config.quiet_start, config.quiet_end)) {
            return -1;
        }
        return ChimeIndex(hour, config.count);
    }

private:
    std::time_t previous_ = 0;
    int64_t latest_hour_ = -1;
};

}  // namespace flower
#endif  // FLOWER_CHIME_SCHEDULE_H_
