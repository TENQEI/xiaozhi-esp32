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
                self.assertEqual((manifest["quiet_start"], manifest["quiet_end"]), (20, 4))
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
                             dict(version=1, count=1, enabled=False, quiet_start=0, quiet_end=0))
            with self.assertRaises(ValueError):
                PREPARE.prepare(source, source / "output")


class FlowerScheduleTest(unittest.TestCase):
    def test_mapping_clock_jumps_quiet_boundaries_busy_hours_and_rollover(self):
        driver = r'''
            #include "chime_schedule.h"
            #include <cassert>
            using namespace flower;
            constexpr std::time_t day = 1762041600; // 2025-11-02 civil midnight
            int main() {
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
