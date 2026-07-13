#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


AES_KEY = b"50755440496e2d32"
AES_IV = b"426c335f44654d33"
DEFAULT_ADDRESS: str | None = None
DEFAULT_SCAN: Path | None = None


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha10(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def aes_encrypt(data: bytes) -> bytes:
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(data, 16))


def aes_decrypt(data: bytes) -> bytes:
    return unpad(AES.new(AES_KEY, AES.MODE_CBC, AES_IV).decrypt(data), 16)


def json_payload(obj: dict[str, Any]) -> bytes:
    raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def extract_js_const(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8", errors="strict")
    match = re.search(rf"\bconst\s+{re.escape(name)}\s*=\s*(['\"])(.*?)\1\s*;", text)
    if not match:
        raise ValueError(f"missing JS constant {name} in {path}")
    return match.group(2)


def read_two_line_secret(path: Path) -> tuple[str, str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(f"{path} must contain SSID on line 1 and password on line 2")
    return lines[0], lines[1]


def load_wifi_secret(args: argparse.Namespace) -> tuple[str, str, str]:
    if args.ssid and args.password:
        return args.ssid, args.password, "argv"
    if args.secret_js:
        path = Path(args.secret_js)
        return extract_js_const(path, "WIFI_SSID"), extract_js_const(path, "WIFI_PASSWORD"), str(path)
    if args.secret_file:
        path = Path(args.secret_file)
        ssid, password = read_two_line_secret(path)
        return ssid, password, str(path)
    raise ValueError("provide --secret-js, --secret-file, or --ssid and --password")


def load_scan_security(path: Path | None, ssid: str) -> tuple[int | None, int, bool]:
    if path is None or not path.exists():
        return None, 0, False
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data:
        if isinstance(item, dict) and item.get("SSID") == ssid:
            return int(item.get("security", 2)), int(item.get("strength", 0)), True
    return None, 0, False


def parse_frame(data: bytes) -> dict[str, Any]:
    if len(data) < 8 or data[0:1] != b"$":
        return {"valid": False, "raw_len": len(data), "raw_hex": data.hex()}
    classic_id = struct.unpack_from("<H", data, 1)[0]
    payload_len = struct.unpack_from("<I", data, 3)[0]
    payload = data[7 : 7 + payload_len]
    trailer = data[7 + payload_len : 8 + payload_len]
    return {
        "valid": len(payload) == payload_len and trailer == b"*",
        "classic_id": classic_id,
        "payload_len": payload_len,
        "payload_hex": payload.hex(),
        "trailer_hex": trailer.hex(),
        "raw_len": len(data),
        "raw_hex": data.hex(),
    }


def recv_frame(sock: socket.socket) -> bytes:
    data = b""
    deadline = time.monotonic() + 20
    expected = None
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except ConnectionResetError:
            return data
        if not chunk:
            break
        data += chunk
        if len(data) >= 7 and data[0:1] == b"$":
            payload_len = struct.unpack_from("<I", data, 3)[0]
            expected = 8 + payload_len
            if len(data) >= expected:
                return data[:expected]
    if expected is not None and len(data) >= expected:
        return data[:expected]
    return data


def classic_request(address: str, channel: int, classic_id: int, payload: bytes, timeout: float) -> bytes:
    frame = b"$" + struct.pack("<H", classic_id) + struct.pack("<I", len(payload)) + payload + b"*"
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, channel))
        sock.sendall(frame)
        return recv_frame(sock)
    finally:
        sock.close()


def classic_longread(address: str, channel: int, classic_id: int, timeout: float) -> tuple[bytes, list[bytes]]:
    request = b"$" + struct.pack("<H", classic_id) + struct.pack("<I", 0) + b"*"
    frames: list[bytes] = []
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, channel))
        sock.sendall(request)
        first = recv_frame(sock)
        frames.append(first)
        parsed = parse_frame(first)
        if not parsed.get("valid"):
            return b"", frames
        payload = bytes.fromhex(parsed.get("payload_hex", ""))
        if len(payload) < 4:
            return payload, frames
        total = struct.unpack_from("<i", payload, 0)[0]
        if total < 0 or total > 5000:
            return payload, frames
        assembled = bytearray(payload[4:])
        while len(assembled) < total:
            sock.sendall(request)
            chunk_frame = recv_frame(sock)
            frames.append(chunk_frame)
            parsed_chunk = parse_frame(chunk_frame)
            if not parsed_chunk.get("valid"):
                break
            chunk = bytes.fromhex(parsed_chunk.get("payload_hex", ""))
            if not chunk:
                break
            assembled.extend(chunk[: total - len(assembled)])
        return bytes(assembled), frames
    finally:
        sock.close()


def decode_wifi_config(payload: bytes) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    if payload == b"\xff\xff\xff\xff":
        return None, None, "no_config"
    try:
        plain = aes_decrypt(payload)
    except Exception as exc:
        return None, None, f"decrypt_error:{type(exc).__name__}"
    candidate = plain
    if len(candidate) >= 4:
        json_len = struct.unpack_from("<I", candidate, 0)[0]
        if 0 < json_len <= len(candidate) - 4:
            candidate = candidate[4 : 4 + json_len]
    try:
        return json.loads(candidate.decode("utf-8")), plain, None
    except Exception as exc:
        return None, plain, f"json_error:{type(exc).__name__}"


def redact_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None
    out = dict(config)
    ssid = str(out.get("last_ssid", ""))
    out["last_ssid"] = {"len": len(ssid), "sha256_10": sha10(ssid) if ssid else ""}
    return out


def write_file(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Dreem Classic Bluetooth Wi-Fi auth writer")
    parser.add_argument("--address", default=DEFAULT_ADDRESS, required=DEFAULT_ADDRESS is None)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--secret-js")
    parser.add_argument("--secret-file")
    parser.add_argument("--ssid")
    parser.add_argument("--password")
    parser.add_argument("--scan-file", default=str(DEFAULT_SCAN) if DEFAULT_SCAN else None)
    parser.add_argument("--security", type=int)
    parser.add_argument("--hidden", type=int, default=0)
    parser.add_argument("--known", type=int, default=0)
    parser.add_argument("--strength", type=int)
    parser.add_argument("--polls", type=int, default=3)
    parser.add_argument("--poll-delay", type=float, default=8.0)
    parser.add_argument("--skip-write", action="store_true")
    parser.add_argument("--out-dir")
    args = parser.parse_args()

    ssid, password, secret_source = load_wifi_secret(args)
    scan_security, scan_strength, matched_scan = load_scan_security(Path(args.scan_file) if args.scan_file else None, ssid)
    security = args.security if args.security is not None else (scan_security if scan_security is not None else 2)
    strength = args.strength if args.strength is not None else scan_strength
    out_dir = Path(args.out_dir) if args.out_dir else Path("evidence") / f"btclassic_wifi_auth_{utc_stamp()}"
    private_dir = out_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)

    wifi = {
        "hidden": int(args.hidden),
        "known": int(args.known),
        "password": password,
        "security": int(security),
        "SSID": ssid,
        "strength": int(strength),
    }
    serialized = json_payload(wifi)
    encrypted = aes_encrypt(serialized)
    if not args.skip_write:
        write_file(private_dir / "201_wifi_auth_payload_plain.bin", serialized)
        write_file(private_dir / "201_wifi_auth_payload_encrypted.bin", encrypted)

    summary: dict[str, Any] = {
        "started_utc": utc_stamp(),
        "address": args.address,
        "channel": args.channel,
        "secret_source": secret_source,
        "ssid": {"len": len(ssid), "sha256_10": sha10(ssid)},
        "password": {"len": len(password)},
        "matched_scan": matched_scan,
        "security": int(security),
        "strength": int(strength),
        "payload": {"plain_len": len(serialized), "encrypted_len": len(encrypted)},
        "steps": [],
    }

    if args.skip_write:
        summary["steps"].append({"op": "write_201_wifi_auth", "skipped": True})
    else:
        step: dict[str, Any] = {"op": "write_201_wifi_auth"}
        try:
            raw = classic_request(args.address, args.channel, 201, encrypted, args.timeout)
            write_file(private_dir / "201_write_response.bin", raw)
            parsed = parse_frame(raw)
            step.update(
                {
                    "response_valid": parsed.get("valid"),
                    "response_len": parsed.get("raw_len"),
                    "payload_len": parsed.get("payload_len"),
                }
            )
            payload = bytes.fromhex(parsed.get("payload_hex", "")) if parsed.get("payload_hex") else b""
            if len(payload) >= 4:
                step["status_le"] = struct.unpack_from("<i", payload, 0)[0]
        except Exception as exc:
            step["exception"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        summary["steps"].append(step)

    for poll in range(args.polls):
        time.sleep(args.poll_delay)
        poll_step: dict[str, Any] = {
            "op": "read_202_wifi_status",
            "poll": poll,
        }
        try:
            raw_202 = classic_request(args.address, args.channel, 202, b"", args.timeout)
            write_file(private_dir / f"202_wifi_status_poll{poll}.bin", raw_202)
            parsed_202 = parse_frame(raw_202)
            payload_202 = bytes.fromhex(parsed_202.get("payload_hex", "")) if parsed_202.get("payload_hex") else b""
            poll_step.update(
                {
                    "response_valid": parsed_202.get("valid"),
                    "payload_len": parsed_202.get("payload_len"),
                }
            )
            if len(payload_202) >= 4:
                poll_step["status_le"] = struct.unpack_from("<i", payload_202, 0)[0]
        except Exception as exc:
            poll_step["exception"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        summary["steps"].append(poll_step)

        time.sleep(4)
        config_step: dict[str, Any] = {
            "op": "read_203_wifi_config",
            "poll": poll,
        }
        try:
            payload_203, frames_203 = classic_longread(args.address, args.channel, 203, args.timeout)
            for frame_idx, frame in enumerate(frames_203):
                write_file(private_dir / f"203_wifi_config_poll{poll}.frame{frame_idx}.bin", frame)
            config, plain, error = decode_wifi_config(payload_203)
            if plain is not None:
                write_file(private_dir / f"203_wifi_config_poll{poll}.decrypted.bin", plain)
            if config is not None:
                write_file(private_dir / f"203_wifi_config_poll{poll}.decrypted.json", json.dumps(config, indent=2, sort_keys=True))
            config_step.update(
                {
                    "frames": len(frames_203),
                    "assembled_len": len(payload_203),
                    "decode_error": error,
                    "config": redact_config(config),
                }
            )
        except Exception as exc:
            config_step["exception"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        summary["steps"].append(config_step)

    summary["finished_utc"] = utc_stamp()
    write_file(out_dir / "summary.json", json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
