"""Verify weekday/weekend selection and chime policy across civil-date changes."""

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"


class FlowerCalendarTest(unittest.TestCase):
    def test_weekdays_weekends_and_overnight_transitions(self):
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
                return {24, true, GreetingsForDate(schedule, now), true, true};
            }
            int Event(const GreetingSchedule& settings, std::time_t now) {
                ChimeSchedule scheduler;
                scheduler.Poll(now-1, Config(settings, now-1), true);
                return scheduler.Poll(now, Config(settings, now), true);
            }
            int main() {
                GreetingSchedule settings{{480, 1200}, {570, 1290}};
                assert(ValidSchedule(settings));
                assert(!ValidSchedule({{-1, 1200}, {570, 1290}}));
                assert(GreetingsForDate(settings, Date(2026,11,6)).MorningMinute()==480); // Friday
                assert(GreetingsForDate(settings, Date(2026,11,7)).MorningMinute()==570);
                assert(GreetingsForDate(settings, Date(2026,11,8)).MorningMinute()==570);
                assert(GreetingsForDate(settings, Date(2026,11,9)).MorningMinute()==480);
                // Fixed weekdays: makeup Sundays remain weekend, and weekday
                // public holidays remain weekdays. No annual holiday data is needed.
                assert(GreetingsForDate(settings, Date(2026,1,4)).MorningMinute()==570);
                assert(GreetingsForDate(settings, Date(2026,1,2)).MorningMinute()==480);
                assert(GreetingsForDate(settings, Date(2027,1,1)).MorningMinute()==480);
                assert(GreetingsForDate(settings, Date(2027,1,2)).MorningMinute()==570);
                // The OTA-adjusted civil clock must not receive a second TZ offset.
                setenv("TZ", "CST-8", 1); tzset();
                assert(GreetingsForDate(settings, Date(2026,11,6,23,59)).MorningMinute()==480);
                assert(GreetingsForDate(settings, Date(2026,11,7)).MorningMinute()==570);

                assert(Event(settings, Date(2026,11,5,20))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,6,20))==20);
                assert(Event(settings, Date(2026,11,6,21,30))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,6,22))==-1);
                assert(Event(settings, Date(2026,11,7))==-1); // midnight remains quiet
                assert(Event(settings, Date(2026,11,7,8))==-1);
                assert(Event(settings, Date(2026,11,7,9))==-1);
                assert(Event(settings, Date(2026,11,7,9,30))==ChimeSchedule::kGoodMorning);
                assert(Event(settings, Date(2026,11,7,10))==10);
                assert(Event(settings, Date(2026,11,7,21,30))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,8,9,30))==ChimeSchedule::kGoodMorning);
                assert(Event(settings, Date(2026,11,8,20))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,8,21,30))==-1);
                assert(Event(settings, Date(2026,11,9,7))==-1);
                assert(Event(settings, Date(2026,11,9,8))==ChimeSchedule::kGoodMorning);
                assert(Event(settings, Date(2026,1,4,8))==-1);
                assert(Event(settings, Date(2026,1,2,8))==ChimeSchedule::kGoodMorning);
                settings.restday={540,540}; // disable only weekend quiet/greetings
                assert(Event(settings, Date(2026,11,6,8))==ChimeSchedule::kGoodMorning);
                assert(Event(settings, Date(2026,11,6,21))==21);
                assert(Event(settings, Date(2026,11,7,9))==9);
                assert(Event(settings, Date(2026,11,8,20))==ChimeSchedule::kGoodNight);
                assert(Event(settings, Date(2026,11,9,8))==ChimeSchedule::kGoodMorning);
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
