#!/usr/bin/env python3
"""Recover HDF5 candidates from a raw Dreem storage image."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys


HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"
CHUNK_SIZE = 1024 * 1024


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_int(text: str) -> int:
    return int(text, 0)


def find_magic_offsets(path: Path) -> list[int]:
    offsets: list[int] = []
    base = 0
    overlap = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            data = overlap + chunk
            search_from = 0
            while True:
                hit = data.find(HDF5_MAGIC, search_from)
                if hit < 0:
                    break
                absolute = base - len(overlap) + hit
                if absolute >= 0:
                    offsets.append(absolute)
                search_from = hit + 1
            keep = max(0, len(HDF5_MAGIC) - 1)
            overlap = data[-keep:]
            base += len(chunk)
    return offsets


def validate_h5(path: Path) -> dict[str, object]:
    if shutil.which("h5ls") is None:
        return {"h5ls_ok": False, "h5ls_error": "h5ls not found"}
    proc = subprocess.run(
        ["h5ls", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )
    return {
        "h5ls_ok": proc.returncode == 0,
        "h5ls_returncode": proc.returncode,
        "h5ls_output": proc.stdout[:4000],
    }


def copy_window(src: Path, dst: Path, *, offset: int, size: int) -> int:
    remaining = size
    copied = 0
    with src.open("rb") as in_file, dst.open("wb") as out_file:
        in_file.seek(offset)
        while remaining > 0:
            chunk = in_file.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            out_file.write(chunk)
            copied += len(chunk)
            remaining -= len(chunk)
    return copied


def carve_image(*, image: Path, out_dir: Path, max_bytes: int, validate: bool = True) -> list[dict[str, object]]:
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    image_size = image.stat().st_size
    results: list[dict[str, object]] = []
    for index, offset in enumerate(find_magic_offsets(image)):
        size = min(max_bytes, image_size - offset)
        candidate = out_dir / f"candidate_{index:03d}_off_{offset:016x}.h5"
        copied = copy_window(image, candidate, offset=offset, size=size)
        result: dict[str, object] = {
            "index": index,
            "offset": offset,
            "offset_hex": f"0x{offset:016x}",
            "path": str(candidate),
            "bytes": copied,
        }
        if validate:
            result.update(validate_h5(candidate))
        results.append(result)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carve HDF5 candidates from a raw image.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--max-bytes", type=parse_int, default=512 * 1024 * 1024)
    parser.add_argument("--no-validate", action="store_true")
    args = parser.parse_args(argv)

    out_dir = args.out_dir or Path("evidence") / f"h5_carve_{stamp()}"
    results = carve_image(
        image=args.image,
        out_dir=out_dir,
        max_bytes=args.max_bytes,
        validate=not args.no_validate,
    )
    manifest = {
        "started_utc": stamp(),
        "image": str(args.image),
        "image_bytes": args.image.stat().st_size,
        "max_bytes": args.max_bytes,
        "candidate_count": len(results),
        "validated_count": sum(1 for item in results if item.get("h5ls_ok")),
        "candidates": results,
        "finished_utc": stamp(),
    }
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["validated_count"] or (args.no_validate and results) else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
