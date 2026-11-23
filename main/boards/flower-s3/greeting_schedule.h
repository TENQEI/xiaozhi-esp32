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

inline bool IsQuietHour(int minute, int start, int end) {
    if (start == end)
        return false;
    return start < end ? minute >= start && minute < end : minute >= start || minute < end;
}

struct GreetingDay {
    GreetingTimes today;
    GreetingTimes tomorrow;

    int MorningMinute() const { return today.morning == today.night ? -1 : today.morning; }
    int NightMinute() const { return tomorrow.morning == tomorrow.night ? -1 : tomorrow.night; }

    bool IsQuiet(int minute) const {
        // The previous evening used today's schedule. The upcoming evening uses tomorrow's.
        return (today.night > today.morning && minute < today.morning) ||
               (minute >= tomorrow.night && IsQuietHour(minute, tomorrow.night, tomorrow.morning));
    }
};

inline bool IsRestDay(int weekday) { return weekday == 0 || weekday == 6; }

// OTA has already shifted the clock to local civil time. Decode with gmtime_r,
// not localtime_r/TZ, to avoid applying the timezone offset a second time.
inline GreetingDay GreetingsForDate(const GreetingSchedule& schedule, std::time_t now) {
    std::tm date = {};
    if (!gmtime_r(&now, &date)) {
        return {schedule.workday, schedule.workday};
    }
    return {IsRestDay(date.tm_wday) ? schedule.restday : schedule.workday,
            IsRestDay((date.tm_wday + 1) % 7) ? schedule.restday : schedule.workday};
}

}  // namespace flower
#endif  // FLOWER_GREETING_SCHEDULE_H_
