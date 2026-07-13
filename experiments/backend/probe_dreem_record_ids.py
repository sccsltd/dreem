#!/usr/bin/env python3
"""Probe narrowly-scoped Dreem record/report routes for specific record IDs.

Prints only response metadata. Bodies are saved under a restricted evidence
directory for later inspection.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE = "https://api.rythm.co/v1/dreem"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def auth_header(token_file: Path) -> str:
    token = token_file.read_text().strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def request(method: str, url: str, authorization: str, body: bytes | None = None):
    headers = {
        "Authorization": authorization,
        "Accept": "application/json, */*",
        "User-Agent": "Dreem/478 Android",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=25) as resp:
            data = resp.read()
            return resp.status, dict(resp.headers.items()), data
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except URLError as exc:
        return 0, {}, str(exc).encode("utf-8")


def summarize(status: int, headers: dict[str, str], data: bytes) -> dict[str, object]:
    summary: dict[str, object] = {
        "status": status,
        "bytes": len(data),
        "content_type": headers.get("Content-Type") or headers.get("content-type"),
        "sha256_16": hashlib.sha256(data).hexdigest()[:16],
        "hdf5_magic": data.startswith(b"\x89HDF\r\n\x1a\n"),
    }
    try:
        parsed = json.loads(data.decode("utf-8"))
        if isinstance(parsed, dict):
            summary["json_keys"] = sorted(parsed.keys())[:30]
            for key in ["reference", "id", "night", "report", "h5file", "edffile", "algo_did_run"]:
                if key in parsed:
                    summary[key] = parsed[key]
        else:
            summary["json_type"] = type(parsed).__name__
    except Exception:
        pass
    return summary


def save_response(outdir: Path, idx: int, label: str, status: int, headers: dict[str, str], data: bytes):
    safe_label = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in label)[:160]
    body_path = outdir / f"{idx:02d}_{safe_label}.body"
    meta_path = outdir / f"{idx:02d}_{safe_label}.json"
    body_path.write_bytes(data)
    meta = summarize(status, headers, data)
    meta["body_file"] = body_path.name
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    return meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("record_ids", nargs="+")
    args = parser.parse_args()

    outdir = args.outdir or Path(f"evidence/backend_probes/app_log_record_probe_{stamp()}")
    outdir.mkdir(parents=True, mode=0o700)
    outdir.chmod(0o700)
    authorization = auth_header(args.token_file)

    summary: list[dict[str, object]] = []
    idx = 0
    for record_id in args.record_ids:
        idx += 1
        url = f"{API_BASE}/algorythm/record/{record_id}/"
        status, headers, data = request("GET", url, authorization)
        meta = save_response(outdir, idx, f"GET_algorythm_record_{record_id}", status, headers, data)
        meta.update({"record_id": record_id, "route": "algorythm_record"})
        summary.append(meta)

        filenames = [record_id]
        reference = meta.get("reference")
        if reference is not None:
            reference = str(reference)
            if reference not in filenames:
                filenames.insert(0, reference)
        for filename in filenames:
            idx += 1
            h5_url = f"{API_BASE}/algorythm/record/{record_id}/h5/?filename={filename}"
            status, headers, data = request("GET", h5_url, authorization)
            h5_meta = save_response(
                outdir, idx, f"GET_h5_{record_id}_{filename}", status, headers, data
            )
            h5_meta.update({"record_id": record_id, "filename": filename, "route": "h5"})
            summary.append(h5_meta)

        idx += 1
        detail_body = json.dumps({"report_id": record_id}).encode("utf-8")
        status, headers, data = request(
            "POST", f"{API_BASE}/record/report/details/", authorization, body=detail_body
        )
        detail_meta = save_response(outdir, idx, f"POST_report_details_{record_id}", status, headers, data)
        detail_meta.update({"record_id": record_id, "route": "report_details"})
        summary.append(detail_meta)

    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"outdir": str(outdir), "summary": summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
