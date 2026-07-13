#!/usr/bin/env python3
"""Watch for a new U-Boot USB mass-storage disk and optionally image it."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 4 * 1024 * 1024


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_int(text: str) -> int:
    return int(text, 0)


def flatten_lsblk(data: dict[str, object]) -> list[dict[str, object]]:
    flat: list[dict[str, object]] = []

    def visit(device: dict[str, object]) -> None:
        flat.append(device)
        for child in device.get("children", []) or []:
            if isinstance(child, dict):
                visit(child)

    for device in data.get("blockdevices", []) or []:
        if isinstance(device, dict):
            visit(device)
    return flat


def current_lsblk_devices() -> list[dict[str, object]]:
    proc = subprocess.run(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--output",
            "NAME,PATH,TYPE,TRAN,RM,SIZE,MODEL,SERIAL,VENDOR,HOTPLUG,MOUNTPOINTS",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "lsblk failed")
    return flatten_lsblk(json.loads(proc.stdout))


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _device_signature(device: dict[str, object]) -> tuple[str, ...]:
    keys = ("type", "tran", "rm", "size", "model", "serial", "vendor", "hotplug")
    return tuple(str(device.get(key) or "") for key in keys)


def select_new_usb_disks(
    devices: list[dict[str, object]],
    *,
    baseline_paths: set[str],
    baseline_devices_by_path: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for device in devices:
        path = str(device.get("path") or "")
        if not path:
            continue
        if path in baseline_paths:
            if baseline_devices_by_path is None:
                continue
            baseline_device = baseline_devices_by_path.get(path)
            if baseline_device and _device_signature(device) == _device_signature(baseline_device):
                continue
        if device.get("type") != "disk":
            continue
        if _int_value(device.get("size")) <= 0:
            continue
        tran = str(device.get("tran") or "").lower()
        hotplug = _int_value(device.get("hotplug"))
        if tran != "usb" and not hotplug:
            continue
        candidates.append(device)
    return candidates


def copy_image(src: Path, dst: Path, *, max_bytes: int | None = None) -> int:
    copied = 0
    remaining = max_bytes
    with src.open("rb") as in_file, dst.open("wb") as out_file:
        while remaining is None or remaining > 0:
            size = CHUNK_SIZE if remaining is None else min(CHUNK_SIZE, remaining)
            chunk = in_file.read(size)
            if not chunk:
                break
            out_file.write(chunk)
            copied += len(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return copied


def run_carver(image: Path, out_dir: Path, max_candidate_bytes: int) -> dict[str, object]:
    from tools import dreem_h5_carve

    carve_dir = out_dir / "h5_carve"
    candidates = dreem_h5_carve.carve_image(
        image=image,
        out_dir=carve_dir,
        max_bytes=max_candidate_bytes,
        validate=True,
    )
    manifest = {
        "started_utc": stamp(),
        "image": str(image),
        "candidate_count": len(candidates),
        "validated_count": sum(1 for item in candidates if item.get("h5ls_ok")),
        "candidates": candidates,
        "finished_utc": stamp(),
    }
    carve_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    (carve_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"manifest": str(carve_dir / "manifest.json"), **manifest}


def write_summary(out_dir: Path, summary: dict[str, object]) -> None:
    summary["finished_utc"] = stamp()
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def watch(
    *,
    out_dir: Path,
    duration: float,
    poll_interval: float,
    once: bool,
    dump: bool,
    max_bytes: int | None = None,
    carve: bool = True,
    carve_max_bytes: int = 512 * 1024 * 1024,
    lister=current_lsblk_devices,
) -> int:
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    started = stamp()
    baseline = lister()
    baseline_paths = {str(device.get("path")) for device in baseline if device.get("path")}
    baseline_devices_by_path = {
        str(device.get("path")): device for device in baseline if device.get("path")
    }
    deadline = time.monotonic() + duration
    events: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []

    while True:
        devices = lister()
        candidates = select_new_usb_disks(
            devices,
            baseline_paths=baseline_paths,
            baseline_devices_by_path=baseline_devices_by_path,
        )
        events.append({"utc": stamp(), "candidates": candidates})
        if candidates:
            break
        if once or time.monotonic() >= deadline:
            break
        time.sleep(poll_interval)

    summary: dict[str, object] = {
        "started_utc": started,
        "duration": duration,
        "poll_interval": poll_interval,
        "baseline_paths": sorted(baseline_paths),
        "events": events,
        "disk_detected": bool(candidates),
        "candidates": candidates,
    }

    if candidates and dump:
        source = Path(str(candidates[0]["path"]))
        image = out_dir / f"ums_{source.name}_{stamp()}.img"
        bytes_copied = copy_image(source, image, max_bytes=max_bytes)
        summary["dump"] = {
            "source": str(source),
            "path": str(image),
            "bytes": bytes_copied,
            "max_bytes": max_bytes,
        }
        if carve:
            summary["h5_carve"] = run_carver(image, out_dir, carve_max_bytes)

    write_summary(out_dir, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if candidates else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch for and optionally image a new USB disk.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evidence" / f"ums_dump_watch_{stamp()}")
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dump", action="store_true", help="copy the first new USB disk read-only")
    parser.add_argument("--max-bytes", type=parse_int)
    parser.add_argument("--no-carve", action="store_true")
    parser.add_argument("--carve-max-bytes", type=parse_int, default=512 * 1024 * 1024)
    args = parser.parse_args(argv)
    return watch(
        out_dir=args.out_dir,
        duration=args.duration,
        poll_interval=args.poll_interval,
        once=args.once,
        dump=args.dump,
        max_bytes=args.max_bytes,
        carve=not args.no_carve,
        carve_max_bytes=args.carve_max_bytes,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
