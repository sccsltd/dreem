"""Preserve firmware-related reverse-proxy traffic without modifying it."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from mitmproxy import http


CAPTURE_DIR = Path(os.environ["DREEM_PROXY_CAPTURE_DIR"])
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
URL_PATTERN = re.compile(rb"https://[^\s\"'<>]+")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned[:100] or "root"


def _download_presigned(url: str, stem: str) -> None:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    destination = CAPTURE_DIR / f"{stem}_{digest}.download"
    metadata = CAPTURE_DIR / f"{stem}_{digest}.download.json"
    if destination.exists() or metadata.exists():
        return

    result: dict[str, Any] = {"url_sha256": hashlib.sha256(url.encode()).hexdigest()}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "DreemFirmwareCapture/1"})
        with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        result.update({"ok": True, "bytes": destination.stat().st_size})
    except Exception as exc:  # The failure details are evidence too.
        destination.unlink(missing_ok=True)
        result.update({"ok": False, "error": repr(exc)})

    metadata.write_text(json.dumps(result, indent=2), encoding="utf-8")


def request(flow: http.HTTPFlow) -> None:
    """Allow the BLE configuration to use the shorter tunnel-root API URL."""
    if not flow.request.path.startswith("/v1/dreem/"):
        flow.request.path = "/v1/dreem" + flow.request.path


def response(flow: http.HTTPFlow) -> None:
    if flow.response is None:
        return

    body = flow.response.raw_content or b""
    request_url = flow.request.pretty_url
    content_type = flow.response.headers.get("content-type", "")
    firmware_related = "firmware" in request_url.lower()
    if "json" in content_type.lower() and b"firmware" in body.lower():
        firmware_related = True
    if not firmware_related:
        return

    stamp = f"{int(time.time() * 1000)}_{flow.id[:8]}"
    path_name = _safe_name(flow.request.path.split("?", 1)[0])
    stem = f"{stamp}_{flow.request.method}_{path_name}"

    event = {
        "request": {
            "method": flow.request.method,
            "url": request_url,
            "headers": dict(flow.request.headers.items(multi=True)),
            "body_bytes": len(flow.request.raw_content or b""),
        },
        "response": {
            "status_code": flow.response.status_code,
            "headers": dict(flow.response.headers.items(multi=True)),
            "body_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        },
    }
    (CAPTURE_DIR / f"{stem}.json").write_text(
        json.dumps(event, indent=2), encoding="utf-8"
    )
    (CAPTURE_DIR / f"{stem}.body").write_bytes(body)

    for raw_url in URL_PATTERN.findall(body):
        url = raw_url.decode("utf-8", errors="replace").replace("\\u0026", "&")
        lowered = url.lower()
        if "amazonaws.com" not in lowered:
            continue
        if "x-amz-" not in lowered and "awsaccesskeyid=" not in lowered:
            continue
        threading.Thread(
            target=_download_presigned,
            args=(url, stem),
            daemon=True,
        ).start()
