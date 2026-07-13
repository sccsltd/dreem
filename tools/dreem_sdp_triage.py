#!/usr/bin/env python3
"""Triage Dreem i.MX6ULL SDP mode without touching persistent storage."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSFS_ROOT = Path("/sys/bus/usb/devices")
SDP_VID = "15a2"
SDP_PID = "0080"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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


def run(cmd: list[str], cwd: Path, out: Path, timeout: int = 45) -> dict[str, object]:
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
        text = proc.stdout
        rc = proc.returncode
        error = None
    except Exception as exc:
        text = repr(exc) + "\n"
        rc = None
        error = type(exc).__name__
    out.write_text(text, encoding="utf-8", errors="replace")
    return {
        "cmd": cmd,
        "cwd": display_path(cwd),
        "out": display_path(out),
        "returncode": rc,
        "started_utc": started,
        "finished_utc": stamp(),
        "error": error,
    }


def write_summary(out_dir: Path, summary: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, mode=0o700)
    out_dir.chmod(0o700)
    summary.setdefault("finished_utc", stamp())
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--sysfs-root", type=Path, default=DEFAULT_SYSFS_ROOT)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument(
        "--ocram-write-test",
        action="store_true",
        help="also run the non-persistent OCRAM wrmem smoke test",
    )
    args = parser.parse_args()

    out_dir = args.out_dir or ROOT / "evidence" / f"sdp_triage_{stamp()}"
    summary: dict[str, object] = {
        "started_utc": stamp(),
        "device_id": f"{SDP_VID}:{SDP_PID}",
        "out_dir": display_path(out_dir),
        "commands": [],
    }

    deadline = time.monotonic() + args.timeout
    devices = find_sdp_devices(args.sysfs_root)
    while not devices and not args.no_wait and time.monotonic() < deadline:
        time.sleep(args.poll_interval)
        devices = find_sdp_devices(args.sysfs_root)

    summary["devices"] = devices
    if not devices:
        summary["error"] = "SDP device not present"
        write_summary(out_dir, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2

    missing = [tool for tool in ["imx_usb", "uuu", "lsusb"] if shutil.which(tool) is None]
    if missing:
        summary["error"] = f"missing tools: {', '.join(missing)}"
        write_summary(out_dir, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 2

    commands: list[dict[str, object]] = []
    commands.append(run(["lsusb"], ROOT, out_dir / "lsusb.txt", timeout=10))
    commands.append(run(["uuu", "-lsusb"], ROOT, out_dir / "uuu_lsusb.txt", timeout=10))
    commands.append(
        run(
            ["imx_usb", "-v", "-c", str(ROOT / "recovery" / "imx-usb" / "imx-register-probe.d")],
            ROOT,
            out_dir / "imx_register_probe.log",
            timeout=30,
        )
    )
    commands.append(
        run(
            ["imx_usb", "-v", "-c", str(ROOT / "recovery" / "imx-usb" / "imx-fuse-scan.d")],
            ROOT,
            out_dir / "imx_fuse_scan.log",
            timeout=30,
        )
    )
    commands.append(
        run(
            ["imx_usb", "-v", "-c", str(ROOT / "recovery" / "imx-usb" / "imx-usdhc-state.d")],
            ROOT,
            out_dir / "imx_usdhc_state.log",
            timeout=30,
        )
    )

    uuu_dir = ROOT / "recovery" / "ocram" / "uuu-probes"
    commands.append(
        run(
            ["uuu", "-V", "-v", "sdp_register_triage.uuu"],
            uuu_dir,
            out_dir / "uuu_sdp_register_triage.log",
        )
    )
    if args.ocram_write_test:
        commands.append(
            run(
                ["uuu", "-V", "-v", "ocram_read_write_test.uuu"],
                uuu_dir,
                out_dir / "uuu_ocram_read_write_test.log",
            )
        )

    summary["commands"] = commands
    summary["finished_utc"] = stamp()
    summary["ok"] = all(item.get("returncode") == 0 for item in commands)
    write_summary(out_dir, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
