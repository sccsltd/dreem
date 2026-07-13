#!/usr/bin/env python3
"""Watch for Dreem i.MX SDP recovery and capture triage evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSFS_ROOT = Path("/sys/bus/usb/devices")
SDP_VID = "15a2"
SDP_PID = "0080"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_optional(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def find_sdp_devices(sysfs_root: Path = DEFAULT_SYSFS_ROOT) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for path in sorted(sysfs_root.glob("*")):
        vid = read_optional(path / "idVendor").lower()
        pid = read_optional(path / "idProduct").lower()
        if vid == SDP_VID and pid == SDP_PID:
            devices.append(
                {
                    "sysfs": str(path),
                    "busnum": read_optional(path / "busnum"),
                    "devnum": read_optional(path / "devnum"),
                    "product": read_optional(path / "product"),
                }
            )
    return devices


def run_command(cmd: list[str], cwd: Path, out: Path, timeout: int = 120) -> dict[str, object]:
    started = stamp()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        out.write_text(proc.stdout, encoding="utf-8", errors="replace")
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "out": str(out),
            "started_utc": started,
            "finished_utc": stamp(),
        }
    except Exception as exc:
        out.write_text(repr(exc) + "\n", encoding="utf-8", errors="replace")
        return {
            "cmd": cmd,
            "returncode": None,
            "out": str(out),
            "started_utc": started,
            "finished_utc": stamp(),
            "error": type(exc).__name__,
        }


def write_summary(out_dir: Path, summary: dict[str, object]) -> None:
    summary["finished_utc"] = stamp()
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def watch(
    *,
    sysfs_root: Path,
    out_dir: Path,
    duration: float,
    poll_interval: float,
    once: bool,
    run_triage: bool,
    runner=run_command,
) -> int:
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    started = stamp()
    deadline = time.monotonic() + duration
    events: list[dict[str, object]] = []
    detected: list[dict[str, str]] = []

    while True:
        devices = find_sdp_devices(sysfs_root)
        event = {"utc": stamp(), "devices": devices}
        events.append(event)
        if devices:
            detected = devices
            break
        if once or time.monotonic() >= deadline:
            break
        time.sleep(poll_interval)

    summary: dict[str, object] = {
        "started_utc": started,
        "sysfs_root": str(sysfs_root),
        "duration": duration,
        "poll_interval": poll_interval,
        "events": events,
        "sdp_detected": bool(detected),
        "devices": detected,
    }

    if detected and run_triage:
        triage_dir = out_dir / f"sdp_triage_{stamp()}"
        triage_log = out_dir / "sdp_triage_stdout.log"
        summary["triage"] = runner(
            [
                sys.executable,
                str(ROOT / "tools" / "dreem_sdp_triage.py"),
                "--no-wait",
                "--sysfs-root",
                str(sysfs_root),
                "--out-dir",
                str(triage_dir),
            ],
            ROOT,
            triage_log,
            180,
        )

    write_summary(out_dir, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if detected else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch for Dreem SDP recovery mode.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evidence" / f"sdp_recovery_watch_{stamp()}")
    parser.add_argument("--sysfs-root", type=Path, default=DEFAULT_SYSFS_ROOT)
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-triage", action="store_true")
    args = parser.parse_args(argv)
    return watch(
        sysfs_root=args.sysfs_root,
        out_dir=args.out_dir,
        duration=args.duration,
        poll_interval=args.poll_interval,
        once=args.once,
        run_triage=not args.no_triage,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
