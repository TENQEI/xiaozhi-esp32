#!/usr/bin/env python3
"""Check actual linked embedded symbols and the 8 MB firmware's OTA budget."""
import argparse
import json
import subprocess
import struct
from pathlib import Path

from gen_flower_audio import load_manifest


def ota_budget(partition_table):
    data = Path(partition_table).read_bytes()
    slots = {}
    for offset in range(0, len(data) - 31, 32):
        magic, kind, subtype, address, size = struct.unpack_from("<HBBII", data, offset)
        if magic != 0x50aa:
            break
        if address + size > 8 * 1024 * 1024:
            raise ValueError("partition exceeds 8 MB Flash")
        if kind == 0 and subtype in (0x10, 0x11):
            slots[subtype] = size
    if len(slots) != 2:
        raise ValueError("both OTA application slots are required")
    return min(slots.values())


def verify(manifest_path, elf, app, nm="xtensa-esp32s3-elf-nm", partition_bytes=0x2f0000):
    manifest = load_manifest(manifest_path)
    symbols = {}
    for line in subprocess.check_output([nm, "--defined-only", str(elf)], text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    for item in manifest["audio"]:
        prefix = "_binary_" + Path(item["file"]).stem + "_ogg_"
        if prefix + "start" not in symbols or prefix + "end" not in symbols:
            raise ValueError(f"embedded resource symbols missing: {item['file']}")
        if symbols[prefix + "end"] - symbols[prefix + "start"] != (Path(manifest_path).parent / item["file"]).stat().st_size:
            raise ValueError(f"embedded resource size differs: {item['file']}")
    size = Path(app).stat().st_size
    if size <= 0 or size > partition_bytes:
        raise ValueError(f"application exceeds OTA partition: {size}/{partition_bytes}")
    return dict(audio_files=len(manifest["audio"]), placeholder_files=sum(item["placeholder"] for item in manifest["audio"]),
                app_bytes=size, ota_partition_bytes=partition_bytes, free_bytes=partition_bytes-size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("main/assets/flower/audio_manifest.json"))
    parser.add_argument("--elf", type=Path, default=Path("build/xiaozhi.elf"))
    parser.add_argument("--app", type=Path, default=Path("build/xiaozhi.bin"))
    parser.add_argument("--nm", default="xtensa-esp32s3-elf-nm")
    parser.add_argument("--partition-table", type=Path, default=Path("build/partition_table/partition-table.bin"))
    parser.add_argument("--output", type=Path, default=Path("build/flower-audio-report.json"))
    args = parser.parse_args()
    report = verify(args.manifest, args.elf, args.app, args.nm, ota_budget(args.partition_table))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
