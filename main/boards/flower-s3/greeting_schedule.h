#ifndef FLOWER_GREETING_SCHEDULE_H_
#define FLOWER_GREETING_SCHEDULE_H_

#include <cstdint>
#include <ctime>

namespace flower {

struct GreetingTimes {
    int morning = 8 * 60;
    int night = 20 * 60;
};

struct GreetingSchedule {
    GreetingTimes workday;
    GreetingTimes restday;
};

inline bool ValidTimes(GreetingTimes times) {
    return times.morning >= 0 && times.morning < 1440 && times.night >= 0 && times.night < 1440;
}

inline bool ValidSchedule(const GreetingSchedule& schedule) {
    return ValidTimes(schedule.workday) && ValidTimes(schedule.restday);
}

inline uint32_t PackTimes(GreetingTimes times) {
    return (static_cast<uint32_t>(times.morning) << 16) | static_cast<uint32_t>(times.night);
}

inline GreetingTimes UnpackTimes(uint32_t packed) {
    return {static_cast<int>(packed >> 16), static_cast<int>(packed & 0xffff)};
}

inline bool IsRestDay(const std::tm& date) { return date.tm_wday == 0 || date.tm_wday == 6; }

// OTA has already shifted the clock to local civil time. Decode with gmtime_r,
// not localtime_r/TZ, to avoid applying the timezone offset a second time.
inline GreetingTimes TimesForDate(const GreetingSchedule& schedule, std::time_t now) {
    std::tm date = {};
    if (!gmtime_r(&now, &date)) {
        return schedule.workday;
    }
    return IsRestDay(date) ? schedule.restday : schedule.workday;
}

}  // namespace flower
#endif  // FLOWER_GREETING_SCHEDULE_H_
