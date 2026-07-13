#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any

import dreem_btclassic_wifi_auth as bt


def payload_from_args(args: argparse.Namespace) -> bytes:
    if args.payload_hex is not None:
        return bytes.fromhex(args.payload_hex.replace(":", "").replace(" ", ""))
    if args.payload_text is not None:
        return args.payload_text.encode("utf-8")
    if args.payload_int is not None:
        return struct.pack("<i", args.payload_int)
    if args.payload_uint is not None:
        return struct.pack("<I", args.payload_uint)
    return b""


def summarize_payload(payload: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {
        "len": len(payload),
        "hex_prefix": payload[:32].hex(),
    }
    if len(payload) >= 4:
        out["u32_le"] = struct.unpack_from("<I", payload, 0)[0]
        out["i32_le"] = struct.unpack_from("<i", payload, 0)[0]
    if len(payload) in (1, 4, 8, 12, 16, 17, 23, 36, 64):
        try:
            text = payload.decode("utf-8")
            if all((31 < ord(ch) < 127) or ch in "\r\n\t" for ch in text):
                out["ascii"] = text
        except UnicodeDecodeError:
            pass
    if len(payload) == 16:
        try:
            out["uuid_be"] = str(__import__("uuid").UUID(bytes=payload))
        except Exception:
            pass
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Dreem Classic Bluetooth single request helper")
    parser.add_argument("classic_id", type=int)
    parser.add_argument("--address", default=bt.DEFAULT_ADDRESS, required=bt.DEFAULT_ADDRESS is None)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--out-dir")
    parser.add_argument("--payload-hex")
    parser.add_argument("--payload-text")
    parser.add_argument("--payload-int", type=int)
    parser.add_argument("--payload-uint", type=int)
    parser.add_argument("--longread", action="store_true")
    parser.add_argument("--cooldown", type=float, default=4.0)
    parser.add_argument("--show-payload", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else Path("evidence") / f"btclassic_request_{bt.utc_stamp()}"
    private_dir = out_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    started = bt.utc_stamp()
    summary: dict[str, Any] = {
        "started_utc": started,
        "address": args.address,
        "channel": args.channel,
        "classic_id": args.classic_id,
        "longread": args.longread,
    }

    try:
        if args.longread:
            assembled, frames = bt.classic_longread(args.address, args.channel, args.classic_id, args.timeout)
            for idx, frame in enumerate(frames):
                bt.write_file(private_dir / f"frame_{idx:02d}.bin", frame)
            bt.write_file(private_dir / "assembled_payload.bin", assembled)
            summary["frames"] = len(frames)
            summary["assembled"] = summarize_payload(assembled)
            if args.show_payload:
                summary["assembled"]["hex"] = assembled.hex()
        else:
            payload = payload_from_args(args)
            bt.write_file(private_dir / "request_payload.bin", payload)
            raw = bt.classic_request(args.address, args.channel, args.classic_id, payload, args.timeout)
            bt.write_file(private_dir / "response_frame.bin", raw)
            parsed = bt.parse_frame(raw)
            summary["response"] = {
                "valid": parsed.get("valid"),
                "raw_len": parsed.get("raw_len"),
                "payload_len": parsed.get("payload_len"),
                "classic_id": parsed.get("classic_id"),
            }
            response_payload = bytes.fromhex(parsed.get("payload_hex", "")) if parsed.get("payload_hex") else b""
            summary["payload"] = summarize_payload(response_payload)
            if args.show_payload:
                summary["payload"]["hex"] = response_payload.hex()
        summary["ok"] = True
    except Exception as exc:
        summary["ok"] = False
        summary["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        summary["finished_utc"] = bt.utc_stamp()
        bt.write_file(out_dir / "summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n")
        if args.cooldown > 0:
            time.sleep(args.cooldown)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
