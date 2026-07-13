#!/usr/bin/env python3
"""Generate i.MX HAB DCD CHECK_DATA probes for SDP timing tests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time


HAB_TAG_DCD = 0xD2
HAB_CMD_CHK_DAT = 0xCF
HAB_VERSION_4_0 = 0x40
CHECKDATA_FLAGS = {0x00, 0x08, 0x10, 0x18}
CONDITIONS = {
    "all-clear": 0x00,
    "any-clear": 0x08,
    "all-set": 0x10,
    "any-set": 0x18,
}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSFS_ROOT = Path("/sys/bus/usb/devices")
SDP_VID = "15a2"
SDP_PID = "0080"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_int(text: str) -> int:
    return int(text, 0)


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


def wait_for_sdp_devices(
    *,
    sysfs_root: Path = DEFAULT_SYSFS_ROOT,
    timeout: float = 0,
    poll_interval: float = 1.0,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout
    devices = find_sdp_devices(sysfs_root)
    while not devices and time.monotonic() < deadline:
        time.sleep(poll_interval)
        devices = find_sdp_devices(sysfs_root)
    return devices


def _check_u32(name: str, value: int) -> None:
    if value < 0 or value > 0xFFFFFFFF:
        raise ValueError(f"{name} must fit in uint32")


def _check_width(width: int) -> None:
    if width not in (1, 2, 4):
        raise ValueError("width must be 1, 2, or 4")


def build_dcd_checkdata(*, address: int, mask: int, count: int, width: int = 4, flags: int = 0) -> bytes:
    """Return a DCD blob containing one HAB CHECK_DATA command with a poll count."""

    _check_width(width)
    for name, value in (("address", address), ("mask", mask), ("count", count)):
        _check_u32(name, value)
    if address % width:
        raise ValueError(f"address must be {width}-byte aligned")
    if flags not in CHECKDATA_FLAGS:
        raise ValueError("flags must be one of 0x00, 0x08, 0x10, or 0x18")

    par = flags | width
    command_len = 16
    dcd_len = 4 + command_len
    return b"".join(
        [
            struct.pack(">BHB", HAB_TAG_DCD, dcd_len, HAB_VERSION_4_0),
            struct.pack(">BHBIII", HAB_CMD_CHK_DAT, command_len, par, address, mask, count),
        ]
    )


def write_probe_files(
    *,
    dcd_path: Path,
    uuu_path: Path,
    address: int,
    mask: int,
    count: int,
    width: int = 4,
    flags: int = 0,
) -> None:
    dcd_path.write_bytes(
        build_dcd_checkdata(address=address, mask=mask, count=count, width=width, flags=flags)
    )
    uuu_path.write_text(f"uuu_version 1.4.72\nSDP: dcd -f {dcd_path.name}\n", encoding="utf-8")


def build_bit_campaign(
    *,
    address: int,
    count: int,
    condition: str,
    first_bit: int = 0,
    bit_count: int = 32,
    width: int = 4,
) -> list[dict[str, object]]:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    _check_width(width)
    _check_u32("address", address)
    _check_u32("count", count)
    if address % width:
        raise ValueError(f"address must be {width}-byte aligned")
    if first_bit < 0 or bit_count < 1 or first_bit + bit_count > width * 8:
        raise ValueError("bit range must fit inside the selected width")

    probes: list[dict[str, object]] = []
    for bit in range(first_bit, first_bit + bit_count):
        probes.append(
            {
                "bit": bit,
                "address": address,
                "mask": 1 << bit,
                "count": count,
                "condition": condition,
                "flags": CONDITIONS[condition],
                "width": width,
                "stem": f"bit{bit:02d}",
            }
        )
    return probes


def write_bit_campaign_files(*, out_dir: Path, probes: list[dict[str, object]]) -> Path:
    manifest_probes: list[dict[str, object]] = []
    for probe in probes:
        stem = str(probe["stem"])
        dcd_name = f"{stem}.dcd"
        uuu_name = f"{stem}.uuu"
        write_probe_files(
            dcd_path=out_dir / dcd_name,
            uuu_path=out_dir / uuu_name,
            address=int(probe["address"]),
            mask=int(probe["mask"]),
            count=int(probe["count"]),
            width=int(probe["width"]),
            flags=int(probe["flags"]),
        )
        manifest_probes.append(
            {
                "bit": probe["bit"],
                "address": f"0x{int(probe['address']):08x}",
                "mask": f"0x{int(probe['mask']):08x}",
                "count": probe["count"],
                "condition": probe["condition"],
                "flags": f"0x{int(probe['flags']):02x}",
                "width": probe["width"],
                "dcd": dcd_name,
                "uuu": uuu_name,
            }
        )
    manifest = {"generated_utc": stamp(), "probe_count": len(probes), "probes": manifest_probes}
    manifest_path = out_dir / "campaign_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def finish(out_dir: Path, summary: dict[str, object], rc: int) -> int:
    summary["finished_utc"] = stamp()
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one i.MX SDP HAB CHECK_DATA DCD timing probe."
    )
    parser.add_argument("--address", required=True, type=parse_int)
    parser.add_argument("--mask", type=parse_int)
    parser.add_argument("--count", required=True, type=parse_int)
    parser.add_argument("--condition", choices=sorted(CONDITIONS), default="all-set")
    parser.add_argument("--width", type=int, choices=(1, 2, 4), default=4)
    parser.add_argument("--bit-campaign", action="store_true")
    parser.add_argument("--first-bit", type=int, default=0)
    parser.add_argument("--bit-count", type=int, default=32)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--wait-timeout", type=float, default=0.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--sysfs-root", type=Path, default=DEFAULT_SYSFS_ROOT)
    parser.add_argument("--no-require-sdp", action="store_true")
    args = parser.parse_args(argv)

    out_dir = args.out_dir or ROOT / "evidence" / f"sdp_checkdata_{stamp()}"
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    if args.bit_campaign:
        probes = build_bit_campaign(
            address=args.address,
            count=args.count,
            condition=args.condition,
            first_bit=args.first_bit,
            bit_count=args.bit_count,
            width=args.width,
        )
        manifest_path = write_bit_campaign_files(out_dir=out_dir, probes=probes)
        summary: dict[str, object] = {
            "started_utc": stamp(),
            "mode": "bit-campaign",
            "address": f"0x{args.address:08x}",
            "count": args.count,
            "condition": args.condition,
            "width": args.width,
            "first_bit": args.first_bit,
            "bit_count": args.bit_count,
            "probe_count": len(probes),
            "campaign_manifest": str(manifest_path),
            "ran_uuu": False,
            "note": "Run one generated .uuu file per SDP boot on closed/HAB targets.",
        }
        return finish(out_dir, summary, 0)

    if args.mask is None:
        parser.error("--mask is required unless --bit-campaign is used")

    dcd_path = out_dir / "probe.dcd"
    uuu_path = out_dir / "probe.uuu"
    flags = CONDITIONS[args.condition]

    write_probe_files(
        dcd_path=dcd_path,
        uuu_path=uuu_path,
        address=args.address,
        mask=args.mask,
        count=args.count,
        width=args.width,
        flags=flags,
    )

    summary: dict[str, object] = {
        "started_utc": stamp(),
        "address": f"0x{args.address:08x}",
        "mask": f"0x{args.mask:08x}",
        "count": args.count,
        "condition": args.condition,
        "flags": f"0x{flags:02x}",
        "width": args.width,
        "dcd_path": str(dcd_path),
        "uuu_path": str(uuu_path),
        "ran_uuu": False,
    }

    if not args.dry_run:
        devices = wait_for_sdp_devices(
            sysfs_root=args.sysfs_root,
            timeout=args.wait_timeout,
            poll_interval=args.poll_interval,
        )
        summary["devices"] = devices
        if not devices and not args.no_require_sdp:
            summary["error"] = "SDP device not present"
            return finish(out_dir, summary, 2)
        if shutil.which("uuu") is None:
            summary["error"] = "uuu not found"
            return finish(out_dir, summary, 2)

        started = time.monotonic()
        try:
            proc = subprocess.run(
                ["uuu", "-V", "-v", uuu_path.name],
                cwd=out_dir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
                check=False,
            )
            elapsed = time.monotonic() - started
            (out_dir / "uuu.log").write_text(proc.stdout, encoding="utf-8", errors="replace")
            summary.update(
                {
                    "ran_uuu": True,
                    "returncode": proc.returncode,
                    "elapsed_seconds": elapsed,
                    "uuu_log": str(out_dir / "uuu.log"),
                }
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - started
            text = exc.stdout if isinstance(exc.stdout, str) else ""
            (out_dir / "uuu.log").write_text(text, encoding="utf-8", errors="replace")
            summary.update(
                {
                    "ran_uuu": True,
                    "returncode": None,
                    "elapsed_seconds": elapsed,
                    "uuu_log": str(out_dir / "uuu.log"),
                    "error": "uuu timeout",
                }
            )

    if summary.get("error"):
        return finish(out_dir, summary, 2)
    return finish(out_dir, summary, int(summary.get("returncode", 0) or 0))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
