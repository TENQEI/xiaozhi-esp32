#ifndef FLOWER_GREETING_SCHEDULE_H_
#define FLOWER_GREETING_SCHEDULE_H_

#include <cstdint>
#include <ctime>
#include <initializer_list>

namespace flower {

struct GreetingTimes {
    int morning = 8 * 60;
    int night = 20 * 60;
};

enum class CalendarMode { Daily = 0, Weekdays = 1, ChinaHolidays = 2 };

struct GreetingSchedule {
    CalendarMode mode = CalendarMode::Daily;
    GreetingTimes workday;
    GreetingTimes restday;
};

inline bool ValidTimes(GreetingTimes times) {
    return times.morning >= 0 && times.morning < 1440 && times.night >= 0 && times.night < 1440;
}

inline bool ValidSchedule(const GreetingSchedule& schedule) {
    return static_cast<int>(schedule.mode) >= 0 && static_cast<int>(schedule.mode) <= 2 &&
           ValidTimes(schedule.workday) && ValidTimes(schedule.restday);
}

inline uint32_t PackTimes(GreetingTimes times) {
    return (static_cast<uint32_t>(times.morning) << 16) | static_cast<uint32_t>(times.night);
}

inline GreetingTimes UnpackTimes(uint32_t packed) {
    return {static_cast<int>(packed >> 16), static_cast<int>(packed & 0xffff)};
}

constexpr int kChinaCalendarYear = 2026;

// State Council General Office, 国办发明电〔2025〕7号, 2025-11-04.
// https://www.gov.cn/zhengce/content/202511/content_7047090.htm
// Only published, verified years are covered; never infer future makeup days.
inline bool IsRestDay(const std::tm& date, CalendarMode mode) {
    if (mode == CalendarMode::Daily) {
        return false;
    }
    const bool weekend = date.tm_wday == 0 || date.tm_wday == 6;
    if (mode != CalendarMode::ChinaHolidays || date.tm_year + 1900 != kChinaCalendarYear) {
        return weekend;
    }
    const int mmdd = (date.tm_mon + 1) * 100 + date.tm_mday;
    for (int workday : {104, 214, 228, 509, 920, 1010}) {
        if (mmdd == workday) {
            return false;
        }
    }
    struct Range {
        int first;
        int last;
    };
    for (auto holiday : {Range{101, 103}, Range{215, 223}, Range{404, 406}, Range{501, 505},
                         Range{619, 621}, Range{925, 927}, Range{1001, 1007}}) {
        if (mmdd >= holiday.first && mmdd <= holiday.last) {
            return true;
        }
    }
    return weekend;
}

// OTA has already shifted the clock to local civil time. Decode with gmtime_r,
// not localtime_r/TZ, to avoid applying the timezone offset a second time.
inline GreetingTimes TimesForDate(const GreetingSchedule& schedule, std::time_t now) {
    std::tm date = {};
    if (!gmtime_r(&now, &date)) {
        return schedule.workday;
    }
    return IsRestDay(date, schedule.mode) ? schedule.restday : schedule.workday;
}

}  // namespace flower
#endif  // FLOWER_GREETING_SCHEDULE_H_
