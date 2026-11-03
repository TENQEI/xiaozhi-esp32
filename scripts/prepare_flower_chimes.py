#!/usr/bin/env python3
"""Stage hourly chimes and an independent random phrase pack for Flower S3."""

import argparse
import json
import shutil
import struct
from pathlib import Path

MAX_AUDIO_BYTES = 128 * 1024


def validate_ogg(data):
    if not 4 <= len(data) <= MAX_AUDIO_BYTES:
        raise ValueError("each recording must be nonempty and at most 128 KiB")
    offset, sequence, serial = 0, 0, None
    packet = bytearray()
    packets = []
    ended = False
    while offset < len(data):
        if ended or offset + 27 > len(data) or data[offset:offset + 4] != b"OggS":
            raise ValueError("invalid or truncated Ogg page")
        version, flags = data[offset + 4:offset + 6]
        granule, page_serial, page_sequence = struct.unpack_from("<QII", data, offset + 6)
        segments = data[offset + 26]
        table_end = offset + 27 + segments
        if version or table_end > len(data) or page_sequence != sequence:
            raise ValueError("invalid Ogg version, segment table or page sequence")
        if sequence == 0:
            serial = page_serial
            if flags != 2:
                raise ValueError("recording must start with an Ogg BOS page")
        elif page_serial != serial or flags & 2:
            raise ValueError("chained/multiplexed recordings are not supported")
        if bool(flags & 1) != bool(packet):
            raise ValueError("invalid Ogg continuation")
        cursor = table_end
        for length in data[offset + 27:table_end]:
            if cursor + length > len(data):
                raise ValueError("truncated Ogg body")
            packet.extend(data[cursor:cursor + length])
            cursor += length
            if len(packet) > 2048:
                raise ValueError("Ogg packet exceeds the firmware's 2048-byte limit")
            if length < 255:
                packets.append(bytes(packet))
                packet.clear()
        ended = bool(flags & 4)
        pre_skip = (struct.unpack_from("<H", packets[0], 10)[0]
                    if packets and len(packets[0]) >= 19 else 0)
        if ended and (packet or granule == 2**64 - 1 or granule > 60 * 48000 + pre_skip):
            raise ValueError("incomplete recording or duration exceeds 60 seconds")
        offset = cursor
        sequence += 1
    if not ended or len(packets) < 3:
        raise ValueError("recording must contain complete Opus headers, audio and EOS")
    head = packets[0]
    if (len(head) < 19 or head[:8] != b"OpusHead" or head[8] != 1 or
            head[9] != 1 or head[18] != 0 or not packets[1].startswith(b"OpusTags")):
        raise ValueError("only mono Ogg/Opus recordings with mapping family 0 are supported")
    if any(not p for p in packets[2:]):
        raise ValueError("empty Opus audio packet")


def validate_files(files):
    for file in files:
        if file.stat().st_size > MAX_AUDIO_BYTES:
            raise ValueError(f"{file.name}: recording exceeds 128 KiB")
        try:
            validate_ogg(file.read_bytes())
        except ValueError as error:
            raise ValueError(f"{file.name}: {error}") from error


def prepare(source, output, *, greetings=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError(f"audio directory does not exist: {source}")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("source and staging directories must not overlap")
    config = {"enabled": True, "quiet_start": 20, "quiet_end": 8}
    path = source / "chime-config.json"
    if path.exists():
        custom = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(custom, dict) or set(custom) - set(config):
            raise ValueError("config supports only enabled, quiet_start and quiet_end")
        config.update(custom)
    if type(config["enabled"]) is not bool:
        raise ValueError("enabled must be a boolean")
    for key in ("quiet_start", "quiet_end"):
        if type(config[key]) is not int or not 0 <= config[key] <= 23:
            raise ValueError(f"{key} must be an integer in 0..23")
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".ogg")
    if any(p.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".opus"}
           for p in source.iterdir() if p.is_file()):
        raise ValueError("convert recordings to mono Ogg/Opus before building")
    count = len(files)
    if count not in (0, 1, 12, 24):
        raise ValueError("provide exactly 1, 12 or 24 Ogg recordings (or none to disable)")
    if count > 1:
        expected = ([f"{i:02d}.ogg" for i in range(1, 13)] if count == 12 else
                    [f"{i:02d}.ogg" for i in range(24)])
        if [p.name for p in files] != expected:
            raise ValueError("12 files must be 01.ogg..12.ogg; 24 files must be 00.ogg..23.ogg")
    validate_files(files)
    # Validate before replacing only the files owned by this staging tool.
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("flower_chime_*.ogg"):
        old.unlink()
    for index, file in enumerate(files):
        shutil.copyfile(file, output / f"flower_chime_{index:02d}.ogg")
    greeting_flags = greetings or {"good_morning": False, "good_night": False}
    manifest = {"version": 1, "count": count, **config, **greeting_flags}
    manifest["enabled"] = config["enabled"] and (count > 0 or any(greeting_flags.values()))
    (output / "flower_chime.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    return manifest


def prepare_random(source, output):
    output = Path(output).resolve()
    groups = {name: [] for name in ("common", "morning", "afternoon", "evening")}
    if source is not None:
        source = Path(source).resolve()
        if not source.is_dir():
            raise ValueError(f"random phrase directory does not exist: {source}")
        if source == output or source in output.parents or output in source.parents:
            raise ValueError("source and staging directories must not overlap")
        for directory in (source, *(source / name for name in groups)):
            if not directory.exists():
                continue
            if not directory.is_dir():
                raise ValueError(f"random phrase group must be a directory: {directory}")
            group = "common" if directory == source else directory.name
            for file in sorted(directory.iterdir()):
                if file.name.startswith("."):
                    continue
                if file.is_dir():
                    if directory == source and file.name in groups:
                        continue
                    raise ValueError("random phrase folders must be common, morning, afternoon "
                                     "or evening; no nesting")
                if file.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".opus"}:
                    raise ValueError("convert random phrases to mono Ogg/Opus before building")
                if file.suffix.lower() == ".ogg":
                    groups[group].append(file)
    files = [file for group in groups.values() for file in group]
    if len(files) > 64:
        raise ValueError("provide at most 64 random phrase recordings")
    validate_files(files)
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("flower_random_*.ogg"):
        old.unlink()
    for index, file in enumerate(files):
        shutil.copyfile(file, output / f"flower_random_{index:02d}.ogg")
    manifest = {"version": 2, "count": len(files),
                **{name: len(group_files) for name, group_files in groups.items()}}
    (output / "flower_random.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    return manifest


def prepare_greetings(source, output):
    output = Path(output).resolve()
    expected = {"good_morning.ogg": "flower_greeting_morning.ogg",
                "good_night.ogg": "flower_greeting_night.ogg"}
    files = []
    if source is not None:
        source = Path(source).resolve()
        if not source.is_dir():
            raise ValueError(f"greeting directory does not exist: {source}")
        if source == output or source in output.parents or output in source.parents:
            raise ValueError("source and staging directories must not overlap")
        files = sorted(p for p in source.iterdir() if p.is_file() and
                       not p.name.startswith(".") and p.suffix.lower() == ".ogg")
        if any(p.name not in expected for p in files):
            raise ValueError("greetings must be named good_morning.ogg and/or good_night.ogg")
        if any(p.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".opus"}
               for p in source.iterdir() if p.is_file() and not p.name.startswith(".")):
            raise ValueError("convert greetings to mono Ogg/Opus before building")
    validate_files(files)
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("flower_greeting_*.ogg"):
        old.unlink()
    for file in files:
        shutil.copyfile(file, output / expected[file.name])
    return {"good_morning": any(p.name == "good_morning.ogg" for p in files),
            "good_night": any(p.name == "good_night.ogg" for p in files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--random-source", type=Path)
    parser.add_argument("--greetings-source", type=Path)
    args = parser.parse_args()
    try:
        greetings = prepare_greetings(args.greetings_source, args.output)
        manifest = prepare(args.source, args.output, greetings=greetings)
        random_manifest = prepare_random(args.random_source, args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Flower chimes: {error}\n")
    print(f"Flower chimes: {manifest['count']} recordings; enabled={manifest['enabled']}")
    print(f"Flower random phrases: {random_manifest['count']} recordings")
    print(f"Flower greetings: morning={greetings['good_morning']}; night={greetings['good_night']}")


if __name__ == "__main__":
    main()
