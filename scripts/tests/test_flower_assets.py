import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from gen_flower_audio import generate, load_manifest
from generate_flower_placeholders import generate as placeholders
from verify_flower_firmware import verify, ota_budget
import struct

ASSETS = ROOT / "main/assets/flower"


class FlowerEmbeddedAssetsTest(unittest.TestCase):
    def test_manifest_all_files_decode_and_placeholders_never_overwrite(self):
        manifest = load_manifest(ASSETS / "audio_manifest.json")
        self.assertEqual(len(manifest["audio"]), 56)
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg needed to verify actual decoding")
        for item in manifest["audio"]:
            pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(ASSETS / item["file"]),
                                           "-f", "s16le", "-ac", "1", "-ar", "16000", "-"])
            if item["placeholder"]:
                self.assertAlmostEqual(len(pcm) / 32000, manifest["placeholder_duration_s"], delta=0.005)
            else:
                self.assertGreater(len(pcm), 0)
                self.assertLessEqual(len(pcm) / 32000, 60)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            shutil.copyfile(ASSETS / "audio_manifest.json", folder / "audio_manifest.json")
            for item in manifest["audio"]:
                shutil.copyfile(ASSETS / item["file"], folder / item["file"])
            before = {p.name: hashlib.sha256(p.read_bytes()).digest() for p in folder.glob("*.ogg")}
            placeholders(folder / "audio_manifest.json")
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).digest() for p in folder.glob("*.ogg")})

    def test_manifest_rejects_missing_extra_invalid_or_duplicate_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "flower"
            shutil.copytree(ASSETS, folder)
            path = folder / "audio_manifest.json"
            original = path.read_text()
            manifest = json.loads(original)
            manifest["audio"][0]["file"] = "../outside.ogg"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): load_manifest(path)
            path.write_text(original)
            (folder / "extra.ogg").write_bytes(b"bad")
            with self.assertRaises(ValueError): load_manifest(path)
            (folder / "extra.ogg").unlink()
            (folder / "clock_01.ogg").write_bytes(b"not an ogg")
            with self.assertRaises(ValueError): load_manifest(path)

    def test_manifest_accepts_additional_phrase_and_session_clips(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "flower"
            shutil.copytree(ASSETS, folder)
            path = folder / "audio_manifest.json"
            manifest = json.loads(path.read_text())
            for category in ("phrase_anytime", "session_start"):
                item = next(dict(row) for row in manifest["audio"] if row["category"] == category)
                source = folder / item["file"]
                item.update(id=f"{category.upper()}_99", file=f"{category}_99.ogg")
                shutil.copyfile(source, folder / item["file"])
                manifest["audio"].append(item)
            path.write_text(json.dumps(manifest))
            header = folder / "audio.h"
            generate(path, header)
            self.assertIn("PHRASE_ANYTIME_99", header.read_text())
            self.assertIn("SESSION_START_99", header.read_text())
            self.assertIn("std::array<Clip,5> SESSION_START", header.read_text())

    def test_manifest_rejects_duplicate_missing_required_and_runtime_overflow(self):
        original = json.loads((ASSETS / "audio_manifest.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audio_manifest.json"
            duplicate = dict(original, audio=original["audio"] + [original["audio"][-1]])
            missing = dict(original, audio=original["audio"][1:])
            overflow = dict(original, audio=list(original["audio"]))
            template = next(row for row in original["audio"] if row["category"] == "phrase_anytime")
            for number in range(100, 165):
                item = dict(template, id=f"PHRASE_ANYTIME_{number}", file=f"phrase_anytime_{number}.ogg")
                overflow["audio"].append(item)
            for manifest in (duplicate, missing, overflow):
                path.write_text(json.dumps(manifest))
                with self.subTest(recordings=len(manifest["audio"])):
                    with self.assertRaises(ValueError):
                        load_manifest(path, validate_audio=False)

    def test_cmake_rebuilds_manifest_and_rejects_file_set_changes(self):
        cmake = shutil.which("cmake")
        if not cmake:
            self.skipTest("cmake required")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            assets = folder / "assets"
            shutil.copytree(ASSETS, assets)
            (folder / "CMakeLists.txt").write_text(f'''cmake_minimum_required(VERSION 3.16)
project(FlowerAssetsHost NONE)
set(PROJECT_DIR "{ROOT}")
set(FLOWER_AUDIO_SOURCE_DIR "{assets}")
include("{ROOT}/main/boards/flower-s3/flower_assets.cmake")
''')
            build = folder / "build"
            def run(*args):
                return subprocess.run([cmake, *map(str, args)], capture_output=True, text=True)
            configured = run("-S", folder, "-B", build)
            self.assertEqual(configured.returncode, 0, configured.stdout + configured.stderr)
            header = build / "generated/flower/flower_audio_assets.h"
            self.assertIn("CLOCK_01_ENABLED = true", header.read_text())
            path = assets / "audio_manifest.json"
            manifest = json.loads(path.read_text())
            manifest["audio"][0]["enabled"] = False
            path.write_text(json.dumps(manifest))
            rebuilt = run("--build", build, "--target", "flower_audio_generated")
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
            self.assertIn("CLOCK_01_ENABLED = false", header.read_text())
            extra = assets / "extra.ogg"
            shutil.copyfile(assets / "clock_01.ogg", extra)
            self.assertNotEqual(run("--build", build, "--target", "flower_audio_generated").returncode, 0)
            extra.unlink()
            (assets / "clock_01.ogg").unlink()
            self.assertNotEqual(run("--build", build, "--target", "flower_audio_generated").returncode, 0)

    def test_actual_partition_table_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            table = Path(directory) / "partition-table.bin"
            def entry(kind, subtype, offset, size):
                return struct.pack("<HBBII16sI", 0x50aa, kind, subtype, offset, size, b"test", 0)
            slots = entry(0, 0x10, 0x20000, 0x2f0000) + entry(0, 0x11, 0x310000, 0x2f0000)
            table.write_bytes(slots + b"\xff" * 32)
            self.assertEqual(ota_budget(table), 0x2f0000)
            table.write_bytes(slots + entry(1, 0x82, 0x700000, 0x200000))
            with self.assertRaises(ValueError): ota_budget(table)
            table.write_bytes(entry(0, 0x10, 0x20000, 0x2f0000))
            with self.assertRaises(ValueError): ota_budget(table)

    def test_generated_symbols_link_and_match_actual_bytes(self):
        if not shutil.which("ld") or not shutil.which("nm"):
            self.skipTest("host binutils needed")
        version = subprocess.run(["ld", "--version"], capture_output=True, text=True)
        if "GNU" not in version.stdout:
            self.skipTest("GNU ld binary embedding is required")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = generate(ASSETS / "audio_manifest.json", folder / "flower_audio_assets.h")
            for item in manifest["audio"]:
                shutil.copyfile(ASSETS / item["file"], folder / item["file"])
            subprocess.run(["ld", "-r", "-b", "binary", "-o", "audio.o"] +
                           [item["file"] for item in manifest["audio"]], cwd=folder, check=True)
            source = folder / "test.cc"
            source.write_text('''#include "flower_audio_assets.h"
#include <cassert>
int main() {
using namespace Flower::Sounds;
assert(CLOCK.size()==12 && PHRASE_ANYTIME.size()==19 && SESSION_START.size()==4 && STARTUP.size()==1);
assert(CLOCK_01.substr(0,4)=="OggS" && GREETING_NIGHT.substr(0,4)=="OggS");
}''')
            compiler = shlex.split(os.environ.get("CXX", "c++"))
            executable = folder / "test"
            subprocess.run(compiler + ["-std=c++20", str(source), str(folder / "audio.o"),
                                       "-o", str(executable)], check=True)
            subprocess.run([str(executable)], check=True)
            report = verify(ASSETS / "audio_manifest.json", executable, executable, "nm")
            self.assertEqual(report["audio_files"], 56)
            self.assertGreater(report["free_bytes"], 0)
            with self.assertRaises(ValueError):
                verify(ASSETS / "audio_manifest.json", executable, executable, "nm", 1)


if __name__ == "__main__": unittest.main()
