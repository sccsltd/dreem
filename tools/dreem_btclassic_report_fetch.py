#!/usr/bin/env python3
"""Fetch Dreem report-bearing Bluetooth Classic IDs without SSH.

The app maps latest report UUIDs to IDs 601/952 and report ZIP payloads to
602/951. This helper keeps the raw payloads private and prints only metadata.
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

import dreem_btclassic_wifi_auth as bt


REPORT_IDS = {
    601: "latest_report_uuid",
    602: "latest_report_zip",
    952: "latest_pharma_report_uuid",
    951: "latest_pharma_report_zip",
}


def parse_frame_relaxed(data: bytes) -> dict[str, Any]:
    if len(data) < 7 or data[0:1] != b"$":
        return {"valid": False, "raw_len": len(data), "raw_hex_head": data[:16].hex()}
    classic_id = struct.unpack_from("<H", data, 1)[0]
    payload_len = struct.unpack_from("<I", data, 3)[0]
    payload_end = 7 + payload_len
    if len(data) < payload_end:
        return {
            "valid": False,
            "classic_id": classic_id,
            "payload_len": payload_len,
            "raw_len": len(data),
            "error": "truncated_payload",
        }
    trailer = data[payload_end : payload_end + 1]
    return {
        "valid": True,
        "classic_id": classic_id,
        "payload_len": payload_len,
        "payload_hex": data[7:payload_end].hex(),
        "raw_len": len(data),
        "trailer_present": trailer == b"*",
        "extra_len": max(0, len(data) - payload_end),
    }


def summarize_payload(payload: bytes) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "len": len(payload),
        "sha256_16": __import__("hashlib").sha256(payload).hexdigest()[:16],
        "hex_head": payload[:16].hex(),
        "hdf5_magic": payload.startswith(b"\x89HDF\r\n\x1a\n"),
        "zip_magic": payload.startswith(b"PK\x03\x04"),
    }
    if len(payload) == 1:
        summary["zero_uuid_sentinel"] = payload.hex()
    if len(payload) == 16:
        try:
            summary["uuid_be"] = str(UUID(bytes=payload))
        except ValueError:
            pass
    if len(payload) >= 4:
        summary["u32_le"] = struct.unpack_from("<I", payload, 0)[0]
    return summary


def recv_longread(address: str, channel: int, classic_id: int, timeout: float, max_total: int) -> tuple[bytes, list[bytes], dict[str, Any]]:
    request = b"$" + struct.pack("<H", classic_id) + struct.pack("<I", 0) + b"*"
    frames: list[bytes] = []
    meta: dict[str, Any] = {"classic_id": classic_id}
    sock = __import__("socket").socket(
        __import__("socket").AF_BLUETOOTH,
        __import__("socket").SOCK_STREAM,
        __import__("socket").BTPROTO_RFCOMM,
    )
    sock.settimeout(timeout)
    try:
        sock.connect((address, channel))
        sock.sendall(request)
        first = bt.recv_frame(sock)
        frames.append(first)
        parsed = parse_frame_relaxed(first)
        meta["first_frame"] = {
            "valid": parsed.get("valid"),
            "raw_len": parsed.get("raw_len"),
            "payload_len": parsed.get("payload_len"),
        }
        payload = bytes.fromhex(parsed.get("payload_hex", "")) if parsed.get("payload_hex") else b""
        if not parsed.get("valid"):
            meta["error"] = "invalid_first_frame"
            return b"", frames, meta
        if len(payload) < 4:
            meta["error"] = "short_first_payload"
            return payload, frames, meta
        total = struct.unpack_from("<I", payload, 0)[0]
        meta["advertised_total"] = total
        if total == 0xFFFFFFFF:
            meta["no_data_sentinel"] = True
            return payload, frames, meta
        if total > max_total:
            meta["error"] = "advertised_total_gt_max"
            meta["max_total"] = max_total
            return payload, frames, meta
        assembled = bytearray(payload[4:])
        while len(assembled) < total:
            sock.sendall(request)
            frame = bt.recv_frame(sock)
            frames.append(frame)
            parsed = parse_frame_relaxed(frame)
            if not parsed.get("valid"):
                meta["error"] = "invalid_chunk_frame"
                break
            chunk = bytes.fromhex(parsed.get("payload_hex", "")) if parsed.get("payload_hex") else b""
            if not chunk:
                meta["error"] = "empty_chunk"
                break
            assembled.extend(chunk[: total - len(assembled)])
        meta["bytes_collected"] = len(assembled)
        meta["frames"] = len(frames)
        return bytes(assembled), frames, meta
    finally:
        sock.close()


def inspect_zip(payload: bytes, out_dir: Path) -> dict[str, Any] | None:
    if not payload.startswith(b"PK\x03\x04"):
        return None
    zip_path = out_dir / "payload.zip"
    zip_path.write_bytes(payload)
    extract_dir = out_dir / "zip"
    extract_dir.mkdir(mode=0o700, exist_ok=True)
    members: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            data = zf.read(info.filename)
            member_path = extract_dir / Path(info.filename).name
            member_path.write_bytes(data)
            h5_ok = False
            h5ls_head = ""
            if data.startswith(b"\x89HDF\r\n\x1a\n"):
                proc = subprocess.run(
                    ["h5ls", str(member_path)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                    check=False,
                )
                h5_ok = proc.returncode == 0
                h5ls_head = proc.stdout[:1000]
            members.append(
                {
                    "name": info.filename,
                    "size": len(data),
                    "sha256_16": __import__("hashlib").sha256(data).hexdigest()[:16],
                    "hdf5_magic": data.startswith(b"\x89HDF\r\n\x1a\n"),
                    "h5ls_ok": h5_ok,
                    "h5ls_head": h5ls_head,
                }
            )
    return {"zip_path": str(zip_path), "extract_dir": str(extract_dir), "members": members}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Dreem Bluetooth Classic report IDs.")
    parser.add_argument("--address", default=bt.DEFAULT_ADDRESS, required=bt.DEFAULT_ADDRESS is None)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-total", type=int, default=20 * 1024 * 1024)
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--ids", default="601,952,602,951", help="comma-separated Classic IDs to query")
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--out-dir", type=Path, default=Path("evidence") / f"btclassic_report_fetch_{bt.utc_stamp()}")
    args = parser.parse_args(argv)
    ids = [int(item.strip(), 0) for item in args.ids.split(",") if item.strip()]

    out_dir: Path = args.out_dir
    private_dir = out_dir / "private"
    private_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    private_dir.chmod(0o700)

    summary: dict[str, Any] = {
        "started_utc": bt.utc_stamp(),
        "address": args.address,
        "channel": args.channel,
        "notes": ["No SSH authentication is attempted by this helper."],
        "results": [],
    }

    for classic_id in ids:
        item_dir = private_dir / str(classic_id)
        item_dir.mkdir(mode=0o700, exist_ok=True)
        item: dict[str, Any] = {"classic_id": classic_id, "name": REPORT_IDS.get(classic_id, "unknown"), "attempts": []}
        for attempt in range(max(1, args.retries)):
            attempt_item: dict[str, Any] = {"attempt": attempt + 1}
            try:
                if classic_id in (601, 952):
                    raw = bt.classic_request(args.address, args.channel, classic_id, b"", args.timeout)
                    (item_dir / f"attempt_{attempt + 1}_response_frame.bin").write_bytes(raw)
                    parsed = parse_frame_relaxed(raw)
                    payload = bytes.fromhex(parsed.get("payload_hex", "")) if parsed.get("payload_hex") else b""
                    (item_dir / f"attempt_{attempt + 1}_payload.bin").write_bytes(payload)
                    attempt_item["frame"] = {
                        "valid": parsed.get("valid"),
                        "raw_len": parsed.get("raw_len"),
                        "payload_len": parsed.get("payload_len"),
                    }
                    attempt_item["payload"] = summarize_payload(payload)
                else:
                    payload, frames, meta = recv_longread(
                        args.address,
                        args.channel,
                        classic_id,
                        args.timeout,
                        args.max_total,
                    )
                    for idx, frame in enumerate(frames):
                        (item_dir / f"attempt_{attempt + 1}_frame_{idx:03d}.bin").write_bytes(frame)
                    (item_dir / f"attempt_{attempt + 1}_payload.bin").write_bytes(payload)
                    attempt_item["longread"] = meta
                    attempt_item["payload"] = summarize_payload(payload)
                    zip_meta = inspect_zip(payload, item_dir / f"attempt_{attempt + 1}")
                    if zip_meta is not None:
                        attempt_item["zip"] = zip_meta
                item["attempts"].append(attempt_item)
                if "error" not in attempt_item:
                    break
            except Exception as exc:
                attempt_item["error"] = f"{type(exc).__name__}: {exc}"
                item["attempts"].append(attempt_item)
                time.sleep(args.cooldown)
        summary["results"].append(item)
        time.sleep(args.cooldown)

    summary["finished_utc"] = bt.utc_stamp()
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    any_h5 = any(
        member.get("h5ls_ok")
        for item in summary["results"]
        for attempt in item.get("attempts", [])
        for member in attempt.get("zip", {}).get("members", [])
    )
    return 0 if any_h5 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
