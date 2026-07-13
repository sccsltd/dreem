#!/usr/bin/env python3
"""Offline decrypt Hawk preferences protected by Facebook Conceal KEY_256.

The private output contains decrypted values and must stay mode 0600. The
redacted output is safe to inspect and contains only metadata about each entry.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SECRET_KEY_RE = re.compile(
    r"(token|auth|password|pass|secret|jwt|bearer|refresh|push)", re.IGNORECASE
)


def android_b64decode(value: str) -> bytes:
    return base64.b64decode("".join(value.split()))


def parse_shared_prefs(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    values: dict[str, str] = {}
    for child in root:
        if child.tag != "string":
            continue
        name = child.attrib.get("name")
        if not name:
            continue
        values[name] = child.text or ""
    return values


def jsonish(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def redact_value(key: str, value) -> dict[str, object]:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    item: dict[str, object] = {
        "type": type(value).__name__,
        "json_length": len(encoded),
        "sha256_16": digest,
    }
    if SECRET_KEY_RE.search(key):
        item["redacted"] = True
    elif isinstance(value, bool) or value is None:
        item["value"] = value
    elif isinstance(value, int) or isinstance(value, float):
        item["value"] = value
    else:
        item["redacted"] = True
    return item


def decrypt_entry(aesgcm: AESGCM, key_name: str, hawk_value: str):
    if "@" not in hawk_value:
        raise ValueError("missing Hawk payload separator")
    prefix, payload = hawk_value.split("@", 1)
    packet = android_b64decode(payload)
    if len(packet) < 30:
        raise ValueError(f"short Conceal packet: {len(packet)} bytes")
    version = packet[0]
    cipher_id = packet[1]
    if version != 1 or cipher_id != 2:
        raise ValueError(f"unexpected Conceal header: version={version} cipher={cipher_id}")
    iv = packet[2:14]
    ciphertext_and_tag = packet[14:]
    aad = packet[:2] + key_name.encode("utf-8")
    plaintext = aesgcm.decrypt(iv, ciphertext_and_tag, aad).decode("utf-8")
    return prefix, plaintext, jsonish(plaintext)


def atomic_write_private_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "pull_dir",
        type=Path,
        help="Pixel app sandbox pull directory containing extract/shared_prefs",
    )
    parser.add_argument("--private-out", type=Path)
    parser.add_argument("--redacted-out", type=Path)
    args = parser.parse_args()

    prefs_dir = args.pull_dir / "extract" / "shared_prefs"
    hawk_path = prefs_dir / "Hawk2.xml"
    key_path = prefs_dir / "crypto.KEY_256.xml"
    private_out = args.private_out or args.pull_dir / "hawk_decrypted_private.json"
    redacted_out = args.redacted_out or args.pull_dir / "hawk_decrypted.redacted.json"

    cipher_key = parse_shared_prefs(key_path).get("cipher_key")
    if not cipher_key:
        print("missing cipher_key", file=sys.stderr)
        return 2
    key = android_b64decode(cipher_key)
    if len(key) != 32:
        print(f"unexpected KEY_256 length: {len(key)}", file=sys.stderr)
        return 2

    aesgcm = AESGCM(key)
    private: dict[str, object] = {}
    redacted: dict[str, object] = {
        "source": str(args.pull_dir),
        "entries": {},
        "summary": {"total": 0, "decrypted": 0, "errors": 0},
    }

    hawk_values = parse_shared_prefs(hawk_path)
    redacted["summary"]["total"] = len(hawk_values)
    for key_name, hawk_value in sorted(hawk_values.items()):
        entry_meta: dict[str, object] = {"hawk_ciphertext_length": len(hawk_value)}
        try:
            prefix, plaintext, converted = decrypt_entry(aesgcm, key_name, hawk_value)
            private[key_name] = {
                "hawk_prefix": prefix,
                "plaintext": plaintext,
                "value": converted,
            }
            entry_meta.update(
                {
                    "ok": True,
                    "hawk_prefix": prefix,
                    "plaintext_length": len(plaintext),
                    "value": redact_value(key_name, converted),
                }
            )
            redacted["summary"]["decrypted"] += 1
        except Exception as exc:  # noqa: BLE001 - evidence output should record all failures.
            private[key_name] = {"error": str(exc)}
            entry_meta.update({"ok": False, "error": str(exc)})
            redacted["summary"]["errors"] += 1
        redacted["entries"][key_name] = entry_meta

    atomic_write_private_json(private_out, private)
    atomic_write_private_json(redacted_out, redacted)

    print(
        json.dumps(
            {
                "private_out": str(private_out),
                "redacted_out": str(redacted_out),
                "summary": redacted["summary"],
            },
            sort_keys=True,
        )
    )
    return 0 if redacted["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
