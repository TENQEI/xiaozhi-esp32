import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main/boards/flower-s3"
SPEC = importlib.util.spec_from_file_location("flower_prepare", ROOT / "scripts/prepare_flower_chimes.py")
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
SOUND = ROOT / "main/assets/locales/zh-CN/1.ogg"


class FlowerAssetsTest(unittest.TestCase):
    def test_all_pack_sizes_preserve_hour_order_and_remove_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            for count in (24, 12, 1, 0):
                source = root / str(count)
                source.mkdir()
                names = (["chime.ogg"] if count == 1 else
                         [f"{i:02d}.ogg" for i in (range(1, 13) if count == 12 else range(count))])
                for i, name in enumerate(names):
                    fixture = SOUND.with_name(f"{i % 10}.ogg")
                    shutil.copyfile(fixture, source / name)
                manifest = PREPARE.prepare(source, output)
                self.assertEqual(manifest["count"], count)
                self.assertEqual(manifest["enabled"], count > 0)
                self.assertEqual((manifest["quiet_start"], manifest["quiet_end"]), (20, 8))
                self.assertEqual(len(list(output.glob("*.ogg"))), count)
                for i, name in enumerate(names):
                    self.assertEqual((output / f"flower_chime_{i:02d}.ogg").read_bytes(),
                                     (source / name).read_bytes())
                self.assertEqual(json.loads((output / "flower_chime.json").read_text()), manifest)

    def test_invalid_counts_names_and_settings_fail_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            output = root / "output"
            for i in range(2):
                shutil.copyfile(SOUND, source / f"{i:02d}.ogg")
            with self.assertRaises(ValueError):
                PREPARE.prepare(source, output)
            for i in range(2, 12):
                shutil.copyfile(SOUND, source / f"{i:02d}.ogg")
            with self.assertRaisesRegex(ValueError, "01.ogg"):
                PREPARE.prepare(source, output)
            for p in source.glob("*.ogg"):
                p.unlink()
            for config in ({"quiet_start": 24}, {"quiet_end": True},
                           {"enabled": "true"}, {"unknown": 1}):
                (source / "chime-config.json").write_text(json.dumps(config))
                with self.assertRaises(ValueError):
                    PREPARE.prepare(source, output)
            self.assertFalse(output.exists())

    def test_malformed_truncated_stereo_and_oversized_recordings_are_rejected(self):
        good = SOUND.read_bytes()
        PREPARE.validate_ogg(good)
        stereo = bytearray(good)
        stereo[stereo.index(b"OpusHead") + 9] = 2
        for data in (b"not audio", good[:-1], good[:100], bytes(stereo),
                     b"OggS" + b"x" * PREPARE.MAX_AUDIO_BYTES, good + good):
            with self.subTest(size=len(data)):
                with self.assertRaises(ValueError):
                    PREPARE.validate_ogg(data)

    def test_disabled_pack_and_no_quiet_window_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            shutil.copyfile(SOUND, source / "chime.ogg")
            (source / "chime-config.json").write_text(
                '{"enabled":false,"quiet_start":0,"quiet_end":0}')
            self.assertEqual(PREPARE.prepare(source, root / "output"),
                             dict(version=1, count=1, enabled=False, quiet_start=0, quiet_end=0,
                                  good_morning=False, good_night=False))
            with self.assertRaises(ValueError):
                PREPARE.prepare(source, source / "output")


class FlowerGreetingPackTest(unittest.TestCase):
    def test_greeting_only_pack_and_independent_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chimes, greetings, phrases = (root / name for name in ("chimes", "greetings", "phrases"))
            for source in (chimes, greetings, phrases):
                source.mkdir()
            output = root / "output"
            shutil.copyfile(SOUND, greetings / "good_morning.ogg")
            shutil.copyfile(SOUND, greetings / "good_night.ogg")
            shutil.copyfile(SOUND, phrases / "hello.ogg")
            PREPARE.prepare_random(phrases, output)
            flags = PREPARE.prepare_greetings(greetings, output)
            manifest = PREPARE.prepare(chimes, output, greetings=flags)
            self.assertEqual(manifest["count"], 0)
            self.assertTrue(manifest["enabled"])
            self.assertTrue(manifest["good_morning"] and manifest["good_night"])
            self.assertEqual((output / "flower_greeting_night.ogg").read_bytes(), SOUND.read_bytes())
            (chimes / "chime-config.json").write_text('{"enabled":false}')
            self.assertFalse(PREPARE.prepare(chimes, output, greetings=flags)["enabled"])
            (greetings / "good_morning.ogg").unlink()
            flags = PREPARE.prepare_greetings(greetings, output)
            self.assertEqual(flags, {"good_morning": False, "good_night": True})
            self.assertFalse((output / "flower_greeting_morning.ogg").exists())
            self.assertTrue((output / "flower_random_00.ogg").exists())
            self.assertTrue((output / "flower_chime.json").exists())
            flags = PREPARE.prepare_greetings(None, output)
            self.assertFalse(any(flags.values()))
            self.assertFalse(list(output.glob("flower_greeting_*.ogg")))

    def test_greetings_validate_names_audio_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "greetings"
            source.mkdir()
            output = root / "output"
            shutil.copyfile(SOUND, source / "morning.ogg")
            with self.assertRaisesRegex(ValueError, "good_morning"):
                PREPARE.prepare_greetings(source, output)
            (source / "morning.ogg").rename(source / "good_morning.ogg")
            (source / "good_morning.ogg").write_bytes(b"not Opus")
            with self.assertRaises(ValueError):
                PREPARE.prepare_greetings(source, output)
            (source / "good_morning.ogg").unlink()
            (source / "good_night.mp3").write_bytes(b"audio")
            with self.assertRaises(ValueError):
                PREPARE.prepare_greetings(source, output)
            with self.assertRaises(ValueError):
                PREPARE.prepare_greetings(source, source / "output")
            with self.assertRaises(ValueError):
                PREPARE.prepare_greetings(root / "missing", output)
            self.assertFalse(output.exists())


class FlowerRandomPackTest(unittest.TestCase):
    def test_independent_random_pack_counts_order_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chimes = root / "chimes"
            chimes.mkdir()
            shutil.copyfile(SOUND, chimes / "chime.ogg")
            output = root / "output"
            PREPARE.prepare(chimes, output)
            for count in (64, 24, 12, 3, 1, 0):
                source = root / f"random-{count}"
                source.mkdir()
                for i in range(count):
                    shutil.copyfile(SOUND.with_name(f"{i % 10}.ogg"), source / f"phrase-{i:02d}.ogg")
                (source / ".ignored.ogg").write_bytes(b"metadata")
                manifest = PREPARE.prepare_random(source, output)
                self.assertEqual(manifest, {"version": 1, "count": count})
                self.assertEqual(len(list(output.glob("flower_random_*.ogg"))), count)
                for i in range(count):
                    self.assertEqual((output / f"flower_random_{i:02d}.ogg").read_bytes(),
                                     (source / f"phrase-{i:02d}.ogg").read_bytes())
                self.assertEqual(json.loads((output / "flower_chime.json").read_text())["count"], 1)
                self.assertTrue((output / "flower_chime_00.ogg").exists())
            self.assertEqual(PREPARE.prepare_random(None, output)["count"], 0)

    def test_invalid_random_count_format_and_paths_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            output = root / "output"
            for i in range(65):
                shutil.copyfile(SOUND, source / f"{i}.ogg")
            with self.assertRaisesRegex(ValueError, "64"):
                PREPARE.prepare_random(source, output)
            for p in source.glob("*.ogg"):
                p.unlink()
            (source / "bad.ogg").write_bytes(b"invalid")
            with self.assertRaises(ValueError):
                PREPARE.prepare_random(source, output)
            (source / "bad.ogg").unlink()
            (source / "unconverted.mp3").write_bytes(b"audio")
            with self.assertRaises(ValueError):
                PREPARE.prepare_random(source, output)
            with self.assertRaises(ValueError):
                PREPARE.prepare_random(source, source / "output")
            with self.assertRaises(ValueError):
                PREPARE.prepare_random(root / "missing", output)
            self.assertFalse(output.exists())


class FlowerScheduleTest(unittest.TestCase):
    def test_mapping_clock_jumps_quiet_boundaries_busy_hours_and_rollover(self):
        driver = r'''
            #include "chime_schedule.h"
            #include "random_phrase.h"
            #include <cassert>
            using namespace flower;
            constexpr std::time_t day = 1762041600; // 2025-11-02 civil midnight
            int main() {
                ChimeConfig defaults{24, true};
                assert(defaults.quiet_start == 20 && defaults.quiet_end == 8);
                defaults.good_morning = defaults.good_night = true;
                for (int h : {7, 8, 19, 20}) {
                    ChimeSchedule schedule;
                    schedule.Poll(day + h * 3600 - 1, defaults, true);
                    int expected = h == 8 ? ChimeSchedule::kGoodMorning :
                                   h == 20 ? ChimeSchedule::kGoodNight :
                                   h == 7 ? -1 : 19;
                    assert(schedule.Poll(day + h * 3600, defaults, true) == expected);
                }
                assert(RandomPhraseIndex(0, 0, -1) == -1);
                assert(RandomPhraseIndex(0, 65, -1) == -1);
                assert(RandomPhraseIndex(UINT32_MAX, 1, 0) == 0);
                for (int count : {2, 3, 12, 24, 64}) {
                    for (int previous = -1; previous <= count; ++previous) {
                        bool seen[64] = {};
                        for (uint32_t random = 0; random < 128; ++random) {
                            int index = RandomPhraseIndex(random, count, previous);
                            assert(index >= 0 && index < count);
                            if (previous >= 0 && previous < count) assert(index != previous);
                            seen[index] = true;
                        }
                        for (int i = 0; i < count; ++i) {
                            assert(seen[i] == (i != previous));
                        }
                    }
                }
                for (int h = 0; h < 24; ++h) {
                    assert(ChimeIndex(h, 1) == 0);
                    assert(ChimeIndex(h, 12) == (h + 11) % 12);
                    assert(ChimeIndex(h, 24) == h);
                    assert(ChimeIndex(h, 2) == -1);
                    assert(IsQuietHour(h, 20, 4) == (h < 4 || h >= 20));
                    assert(IsQuietHour(h, 8, 12) == (h >= 8 && h < 12));
                    assert(!IsQuietHour(h, 0, 0));
                }
                ChimeConfig c{24, true, 20, 4};
                for (int h : {0, 4, 12, 19, 20, 23}) {
                    ChimeSchedule s;
                    assert(s.Poll(day + h * 3600 - 1, c, true) == -1);
                    assert(s.Poll(day + h * 3600, c, true) ==
                           (IsQuietHour(h, 20, 4) ? -1 : h));
                    assert(s.Poll(day + h * 3600 + 1, c, true) == -1);
                }
                ChimeSchedule s;
                assert(s.Poll(0, c, true) == -1);
                assert(s.Poll(day + 12 * 3600, c, true) == -1); // no boot catch-up
                assert(s.Poll(day + 13 * 3600, c, true) == -1); // clock jump
                assert(s.Poll(day + 14 * 3600 - 2, c, true) == -1);
                assert(s.Poll(day + 14 * 3600 + 1, c, false) == -1); // busy, no backlog
                assert(s.Poll(day + 14 * 3600 + 2, c, true) == -1);
                assert(s.Poll(day + 13 * 3600 - 1, c, true) == -1); // clock rollback
                assert(s.Poll(day + 13 * 3600, c, true) == -1);
                assert(s.Poll(day + 15 * 3600 - 1, c, true) == -1);
                assert(s.Poll(day + 15 * 3600 + 6, c, true) == -1); // missed window
                assert(s.Poll(day + 16 * 3600 - 1, c, true) == -1);
                assert(s.Poll(day + 16 * 3600 + 2, c, true) == 16);
                assert(s.Poll(day + 17 * 3600 - 1, c, true) == -1);
                c.enabled = false;
                assert(s.Poll(day + 17 * 3600, c, true) == -1);
                c = {12, true, 0, 0};
                assert(s.Poll(day + 86400 - 1, c, true) == -1);
                assert(s.Poll(day + 86400, c, true) == 11); // next day, 12 o'clock
                // Greetings are exceptions at the quiet boundaries, with priority
                // over ordinary hourly audio. Check wrapped and daytime windows.
                for (auto quiet : {ChimeConfig{24, true, 20, 4, true, true},
                                   ChimeConfig{24, true, 8, 12, true, true},
                                   ChimeConfig{0, true, 0, 8, true, true}}) {
                    for (int hour : {quiet.quiet_start, quiet.quiet_end}) {
                        ChimeSchedule greeting;
                        assert(greeting.Poll(day + hour * 3600 - 1, quiet, true) == -1);
                        int expected = hour == quiet.quiet_start ? ChimeSchedule::kGoodNight
                                                                 : ChimeSchedule::kGoodMorning;
                        assert(greeting.Poll(day + hour * 3600, quiet, true) == expected);
                        assert(greeting.Poll(day + hour * 3600 + 1, quiet, true) == -1);
                    }
                }
                c = {24, true, 20, 4, true, true};
                ChimeSchedule busy;
                busy.Poll(day + 20 * 3600 - 1, c, true);
                assert(busy.Poll(day + 20 * 3600, c, false) == -1);
                assert(busy.Poll(day + 20 * 3600 + 1, c, true) == -1);
                ChimeSchedule jump;
                jump.Poll(day + 19 * 3600, c, true);
                assert(jump.Poll(day + 20 * 3600, c, true) == -1);
                c.enabled = false;
                ChimeSchedule disabled;
                disabled.Poll(day + 4 * 3600 - 1, c, true);
                assert(disabled.Poll(day + 4 * 3600, c, true) == -1);
                c = {24, true, 4, 4, true, true};
                ChimeSchedule no_quiet;
                no_quiet.Poll(day + 4 * 3600 - 1, c, true);
                assert(no_quiet.Poll(day + 4 * 3600, c, true) == 4);
                c = {24, true, 20, 4, false, false};
                ChimeSchedule no_morning;
                no_morning.Poll(day + 4 * 3600 - 1, c, true);
                assert(no_morning.Poll(day + 4 * 3600, c, true) == 4);
            }
        '''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "test.cc"
            source.write_text(driver)
            executable = root / "test"
            command = shlex.split(os.environ.get("CXX", "c++")) + [
                "-std=c++20", "-Wall", "-Wextra", "-Werror", f"-I{BOARD}",
                str(source), "-o", str(executable)]
            subprocess.run(command, check=True)
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
