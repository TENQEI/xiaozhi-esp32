#!/usr/bin/env python3
"""Generate missing 0.4-second mono Opus test tones; never overwrite existing audio."""
import argparse
import math
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from gen_flower_audio import load_manifest


def generate(manifest_path, expected_duration=False):
    manifest = load_manifest(manifest_path, validate_audio=False)
    for index, item in enumerate(manifest["audio"]):
        path = Path(manifest_path).parent / item["file"]
        if path.exists():
            continue
        if not item["placeholder"]:
            raise ValueError(f"missing real recording; refusing to substitute a tone: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "tone.wav"
            samples = []
            frames = round((item["expected_duration_s"] if expected_duration else 0.4) * 16000)
            for n in range(frames):
                envelope = min(1.0, n / 320, (frames - 1 - n) / 320)
                samples.append(int(1600 * envelope * math.sin(2 * math.pi * (440 + index * 15) * n / 16000)))
            with wave.open(str(source), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(struct.pack(f"<{frames}h", *samples))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                            "-i", str(source), "-ac", "1", "-ar", "16000", "-c:a", "libopus",
                            "-b:a", "16k", "-vbr", "off", "-frame_duration", "60",
                            "-application", "voip", str(path)], check=True)
    load_manifest(manifest_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] /
                        "main/assets/flower/audio_manifest.json")
    parser.add_argument("--expected-duration", action="store_true", help="Use planned durations for a separate CI budget fixture")
    args = parser.parse_args()
    generate(args.manifest, args.expected_duration)
