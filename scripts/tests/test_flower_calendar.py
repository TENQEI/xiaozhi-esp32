"""Verify civil-date classification and the real chime policy across day changes."""

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"


class FlowerCalendarTest(unittest.TestCase):
    def test_daily_weekends_holidays_makeup_days_and_overnight_transitions(self):
        driver = r'''
            #include "greeting_schedule.h"
            #include "chime_schedule.h"
            #include <cassert>
            #include <cstdlib>
            using namespace flower;
            std::time_t Date(int year, int month, int day, int hour=0, int minute=0) {
                std::tm value = {};
                value.tm_year=year-1900; value.tm_mon=month-1; value.tm_mday=day;
                value.tm_hour=hour; value.tm_min=minute;
                return timegm(&value);
            }
            ChimeConfig Config(const GreetingSchedule& schedule, std::time_t now) {
                auto times=TimesForDate(schedule, now);
                return {24, true, times.night/60, times.morning/60, true, true,
                        times.night%60, times.morning%60};
            }
            int Event(const GreetingSchedule& settings, std::time_t now) {
                ChimeSchedule scheduler;
                scheduler.Poll(now-1, Config(settings, now-1), true);
                return scheduler.Poll(now, Config(settings, now), true);
            }
            int main() {
                GreetingSchedule settings{CalendarMode::Daily, {480, 1200}, {570, 1335}};
                assert(ValidSchedule(settings));
                assert(!ValidSchedule({static_cast<CalendarMode>(3), {}, {}}));
                for (int day=6; day<=9; ++day) {
                    assert(TimesForDate(settings, Date(2026,11,day)).morning==480);
                }
                settings.mode=CalendarMode::Weekdays;
                assert(TimesForDate(settings, Date(2026,11,6)).morning==480); // Friday
                assert(TimesForDate(settings, Date(2026,11,7)).morning==570);
                assert(TimesForDate(settings, Date(2026,11,8)).morning==570);
                assert(TimesForDate(settings, Date(2026,11,9)).morning==480);
                settings.mode=CalendarMode::ChinaHolidays;
                for (auto date : {Date(2026,1,4), Date(2026,2,14), Date(2026,2,28),
                                  Date(2026,5,9), Date(2026,9,20), Date(2026,10,10)}) {
                    assert(TimesForDate(settings, date).morning==480); // weekend makeup work
                    settings.mode=CalendarMode::Weekdays;
                    assert(TimesForDate(settings, date).morning==570);
                    settings.mode=CalendarMode::ChinaHolidays;
                }
                // All official 2026 rest days, including the weekday portions.
                for (auto range : {std::pair{Date(2026,1,1),3}, std::pair{Date(2026,2,15),9},
                                   std::pair{Date(2026,4,4),3}, std::pair{Date(2026,5,1),5},
                                   std::pair{Date(2026,6,19),3}, std::pair{Date(2026,9,25),3},
                                   std::pair{Date(2026,10,1),7}}) {
                    for (int d=0; d<range.second; ++d) {
                        assert(TimesForDate(settings, range.first+d*86400).morning==570);
                    }
                }
                assert(TimesForDate(settings, Date(2026,10,8)).morning==480);
                assert(TimesForDate(settings, Date(2026,10,11)).morning==570);
                // An unknown year explicitly falls back to Mon-Fri/weekends.
                assert(TimesForDate(settings, Date(2027,1,1)).morning==480);
                assert(TimesForDate(settings, Date(2027,1,2)).morning==570);
                // The OTA-adjusted civil clock must not receive a second TZ offset.
                setenv("TZ", "CST-8", 1); tzset();
                assert(TimesForDate(settings, Date(2026,11,6,23,59)).morning==480);
                assert(TimesForDate(settings, Date(2026,11,7)).morning==570);

                settings.mode=CalendarMode::Weekdays;
                assert(Event(settings, Date(2026,11,6,20))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,7))==-1); // midnight remains quiet
                assert(Event(settings, Date(2026,11,7,8))==-1);
                assert(Event(settings, Date(2026,11,7,9))==-1);
                assert(Event(settings, Date(2026,11,7,9,30))==ChimeSchedule::kGoodMorning);
                assert(Event(settings, Date(2026,11,7,10))==10);
                assert(Event(settings, Date(2026,11,8,22,15))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,9,7))==-1);
                assert(Event(settings, Date(2026,11,9,8))==ChimeSchedule::kGoodMorning);
                settings.mode=CalendarMode::ChinaHolidays;
                assert(Event(settings, Date(2026,1,4,8))==ChimeSchedule::kGoodMorning);
                assert(Event(settings, Date(2026,1,2,8))==-1);
                assert(Event(settings, Date(2026,1,2,9,30))==ChimeSchedule::kGoodMorning);
                settings.restday={540,540}; // disable only rest-day quiet/greetings
                assert(Event(settings, Date(2026,1,2,9))==9);
                assert(Event(settings, Date(2026,1,4,8))==ChimeSchedule::kGoodMorning);
            }
        '''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "calendar.cc"
            source.write_text(driver)
            executable = root / "calendar"
            compiler = shlex.split(os.environ.get("CXX", "c++"))
            subprocess.run(compiler + ["-std=c++20", "-Wall", "-Wextra", "-Werror",
                                       f"-I{BOARD}", str(source), "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
