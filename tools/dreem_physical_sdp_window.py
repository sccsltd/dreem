#!/usr/bin/env python3
"""Coordinate a physical Dreem i.MX6ULL SDP recovery window.

This script assumes a human is performing the TP10-to-GND step. It does not
attempt SSH authentication. It watches for SDP, runs non-persistent triage,
optionally boots the prepared U-Boot UMS payload once, and keeps the USB mass
storage dumper running so a disk is imaged and carved if it appears.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYSFS_ROOT = Path("/sys/bus/usb/devices")
DEFAULT_CHARGER_HELPER = ROOT / "private" / "ha_plug.sh"
DEFAULT_UBOOT = ROOT / "recovery" / "u-boot" / "ums-boot-assets" / "boot_mx6ul_9x9_autoums.uuu"
DEFAULT_UBOOT_MATRIX = [
    DEFAULT_UBOOT,
    ROOT / "recovery" / "u-boot" / "ums-boot-assets" / "boot_mx6ul_14x14_autoums.uuu",
]
DEFAULT_FINGERBOT_BASE = os.environ.get("DREEM_FINGERBOT_BASE_URL", "")
DEFAULT_FINGERBOT_TOKEN_JSON = ROOT / "private" / "fingerbot_login.raw.json"
SDP_VID = "15a2"
SDP_PID = "0080"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_int(text: str) -> int:
    return int(text, 0)


def read_optional(path: Path) -> str:
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def redact_sensitive(text: str) -> str:
    for prefix in ("auth_token=", "token="):
        while prefix in text:
            start = text.index(prefix) + len(prefix)
            end = start
            while end < len(text) and text[end] not in "& \n\r\t\"'":
                end += 1
            text = text[:start] + "<redacted>" + text[end:]
    return text


def load_fingerbot_token(token_json: Path) -> str:
    data = json.loads(token_json.read_text(encoding="utf-8"))
    token = data.get("result", {}).get("token") or data.get("token")
    if not isinstance(token, str) or not token:
        raise ValueError("fingerbot token missing")
    return token


def find_sdp_devices(sysfs_root: Path = DEFAULT_SYSFS_ROOT) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for path in sorted(sysfs_root.glob("*")):
        vid = read_optional(path / "idVendor").lower()
        pid = read_optional(path / "idProduct").lower()
        if vid == SDP_VID and pid == SDP_PID:
            devices.append(
                {
                    "sysfs": str(path),
                    "busnum": read_optional(path / "busnum"),
                    "devnum": read_optional(path / "devnum"),
                    "product": read_optional(path / "product"),
                }
            )
    return devices


def run_command(cmd: list[str], *, cwd: Path, out: Path, timeout: float) -> dict[str, object]:
    started = stamp()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        text = proc.stdout
        rc: int | None = proc.returncode
        error = None
    except subprocess.TimeoutExpired as exc:
        text = exc.stdout if isinstance(exc.stdout, str) else ""
        rc = None
        error = "timeout"
    except Exception as exc:
        text = repr(exc) + "\n"
        rc = None
        error = type(exc).__name__
    out.write_text(text, encoding="utf-8", errors="replace")
    return {
        "cmd": cmd,
        "cwd": str(cwd),
        "out": str(out),
        "returncode": rc,
        "error": error,
        "started_utc": started,
        "finished_utc": stamp(),
    }


def charger(helper: Path, action: str, out_dir: Path) -> dict[str, object]:
    return run_command(
        ["bash", str(helper), action],
        cwd=ROOT,
        out=out_dir / f"charger_{action}_{stamp()}.log",
        timeout=45,
    )


def fingerbot_press(
    *,
    base_url: str,
    token_json: Path,
    press_ms: int,
    angle_enum: str,
    out_dir: Path,
    timeout: float = 45,
    opener=None,
) -> dict[str, object]:
    started = stamp()
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    response_path = out_dir / f"fingerbot_press_{press_ms}_{stamp()}.redacted.json"
    result: dict[str, object] = {
        "action": "fingerbot_press",
        "base_url": base_url.rstrip("/"),
        "press_ms": press_ms,
        "angle_enum": angle_enum,
        "token_json": str(token_json),
        "token_loaded": False,
        "response_redacted": str(response_path),
        "started_utc": started,
    }
    if not base_url:
        body = "ValueError: fingerbot base URL missing; pass --fingerbot-base-url or set DREEM_FINGERBOT_BASE_URL\n"
        response_path.write_text(body, encoding="utf-8", errors="replace")
        result.update({"http_status": None, "error": "ValueError", "finished_utc": stamp()})
        return result
    try:
        token = load_fingerbot_token(token_json)
        result["token_loaded"] = True
    except Exception as exc:
        body = f"{type(exc).__name__}: {exc}\n"
        response_path.write_text(redact_sensitive(body), encoding="utf-8", errors="replace")
        result.update({"http_status": None, "error": type(exc).__name__, "finished_utc": stamp()})
        return result

    query = urllib.parse.urlencode(
        {
            "auth_token": token,
            "press_time": str(press_ms),
            "angle_enum": angle_enum,
        }
    )
    url = f"{base_url.rstrip('/')}/api/fingerbot/click?{query}"
    request = urllib.request.Request(url, method="GET")
    context = ssl._create_unverified_context()
    if opener is None:
        opener = urllib.request.urlopen
    try:
        response = opener(request, timeout=timeout, context=context)
        body_bytes = response.read()
        body = body_bytes.decode("utf-8", errors="replace")
        result.update({"http_status": getattr(response, "status", None), "error": None})
    except Exception as exc:
        body = f"{type(exc).__name__}: {exc}\n"
        result.update({"http_status": None, "error": type(exc).__name__})
    response_path.write_text(redact_sensitive(body), encoding="utf-8", errors="replace")
    result["finished_utc"] = stamp()
    return result


def start_fingerbot_press_thread(
    *,
    base_url: str,
    token_json: Path,
    press_ms: int,
    angle_enum: str,
    out_dir: Path,
) -> tuple[threading.Thread, dict[str, object]]:
    box: dict[str, object] = {}

    def worker() -> None:
        box["result"] = fingerbot_press(
            base_url=base_url,
            token_json=token_json,
            press_ms=press_ms,
            angle_enum=angle_enum,
            out_dir=out_dir,
        )

    thread = threading.Thread(target=worker, name=f"fingerbot_press_{press_ms}", daemon=True)
    thread.start()
    return thread, box


def emit_operator_cue(
    summary: dict[str, object],
    message: str,
    *,
    countdown_seconds: float,
    sleeper=time.sleep,
    printer=print,
) -> None:
    cue = {
        "utc": stamp(),
        "message": message,
        "countdown_seconds": countdown_seconds,
    }
    summary.setdefault("operator_cues", []).append(cue)
    if countdown_seconds > 0:
        printer(f"{message} Charger turns on in {countdown_seconds:g}s.", flush=True)
        sleeper(countdown_seconds)
    else:
        printer(message, flush=True)


def perform_power_cycle(
    args: argparse.Namespace,
    *,
    out_dir: Path,
    summary: dict[str, object],
    sleeper=time.sleep,
    charger_fn=charger,
    press_thread_fn=start_fingerbot_press_thread,
    cue_fn=emit_operator_cue,
) -> None:
    summary["charger_actions"].append(charger_fn(args.charger_helper, "turn_off", out_dir))
    sleeper(args.charger_on_delay)
    cue_message = "Apply and hold the TP10-to-GND short now; charger turn-on follows."
    if args.fingerbot_hold_during_charger_on_ms:
        thread, box = press_thread_fn(
            base_url=args.fingerbot_base_url,
            token_json=args.fingerbot_token_json,
            press_ms=args.fingerbot_hold_during_charger_on_ms,
            angle_enum=args.fingerbot_angle_enum,
            out_dir=out_dir,
        )
        sleeper(args.charger_on_during_hold_delay)
        cue_fn(
            summary,
            cue_message,
            countdown_seconds=args.operator_cue_countdown,
            sleeper=sleeper,
            printer=print,
        )
        summary["charger_actions"].append(charger_fn(args.charger_helper, "turn_on", out_dir))
        thread.join(max(args.fingerbot_hold_during_charger_on_ms / 1000 + 30, 45))
        if thread.is_alive():
            summary["fingerbot_actions"].append(
                {
                    "action": "fingerbot_press",
                    "press_ms": args.fingerbot_hold_during_charger_on_ms,
                    "error": "thread_timeout",
                }
            )
        else:
            summary["fingerbot_actions"].append(box.get("result", {"error": "missing_thread_result"}))
    else:
        cue_fn(
            summary,
            cue_message,
            countdown_seconds=args.operator_cue_countdown,
            sleeper=sleeper,
            printer=print,
        )
        summary["charger_actions"].append(charger_fn(args.charger_helper, "turn_on", out_dir))


def start_ums_watcher(args: argparse.Namespace, out_dir: Path) -> tuple[subprocess.Popen[str], Path]:
    ums_dir = out_dir / "ums_watch"
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "dreem_ums_dump_watch.py"),
        "--out-dir",
        str(ums_dir),
        "--duration",
        str(args.duration + args.post_boot_wait + 30),
        "--poll-interval",
        str(args.ums_poll_interval),
    ]
    if args.dump:
        cmd.append("--dump")
    if args.dump_max_bytes is not None:
        cmd += ["--max-bytes", str(args.dump_max_bytes)]
    if args.no_carve:
        cmd.append("--no-carve")

    log = out_dir / "ums_watch_stdout.log"
    handle = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return proc, log


def stop_process(proc: subprocess.Popen[str], timeout: float = 5) -> int | None:
    if proc.poll() is not None:
        return proc.returncode
    proc.terminate()
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None


def wait_for_ums_summary(proc: subprocess.Popen[str], out_dir: Path, timeout: float) -> dict[str, object]:
    started = time.monotonic()
    summary_path = out_dir / "ums_watch" / "summary.json"
    while time.monotonic() - started < timeout:
        if summary_path.exists():
            try:
                return json.loads(summary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        if proc.poll() is not None:
            break
        time.sleep(1)
    if summary_path.exists():
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid ums summary", "path": str(summary_path)}
    return {"error": "ums summary not written yet", "path": str(summary_path)}


def boot_uboot_scripts(
    scripts: list[Path],
    *,
    out_dir: Path,
    ums_proc: subprocess.Popen[str] | object | None,
    post_boot_wait: float,
    runner=run_command,
    waiter=wait_for_ums_summary,
) -> dict[str, object]:
    attempts: list[dict[str, object]] = []
    ums_summary: dict[str, object] = {}
    for script_path in scripts:
        script = script_path.resolve()
        attempt: dict[str, object] = {"script": str(script)}
        attempt["command"] = runner(
            ["uuu", "-V", "-v", script.name],
            cwd=script.parent,
            out=out_dir / f"uuu_{script.stem}_{stamp()}.log",
            timeout=180,
        )
        if ums_proc is not None:
            ums_summary = waiter(ums_proc, out_dir, post_boot_wait)
            attempt["ums_summary"] = ums_summary
            if ums_summary.get("disk_detected"):
                attempts.append(attempt)
                break
        attempts.append(attempt)
    return {"attempts": attempts, "ums_summary": ums_summary}


def selected_uboot_scripts(args: argparse.Namespace) -> list[Path]:
    if args.try_default_uboot_matrix:
        return DEFAULT_UBOOT_MATRIX
    if args.uboot_script:
        return args.uboot_script
    return [DEFAULT_UBOOT]


def preflight(
    out_dir: Path,
    charger_helper: Path,
    uboot_scripts: list[Path],
    fingerbot_token_json: Path,
) -> dict[str, object]:
    tools = ["python3", "lsusb", "uuu", "imx_usb", "lsblk", "h5ls"]
    result = {
        "tools": {tool: shutil.which(tool) for tool in tools},
        "charger_helper": str(charger_helper),
        "charger_helper_exists": charger_helper.exists(),
        "uboot_script": str(uboot_scripts[0]),
        "uboot_script_exists": uboot_scripts[0].exists(),
        "uboot_scripts": [str(script) for script in uboot_scripts],
        "uboot_scripts_exist": {str(script): script.exists() for script in uboot_scripts},
        "fingerbot_token_json": str(fingerbot_token_json),
        "fingerbot_token_json_exists": fingerbot_token_json.exists(),
        "initial_sdp_devices": find_sdp_devices(),
    }
    (out_dir / "preflight.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coordinate a physical Dreem SDP/UMS recovery window.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evidence" / f"physical_sdp_window_{stamp()}")
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--ums-poll-interval", type=float, default=0.5)
    parser.add_argument("--post-boot-wait", type=float, default=180)
    parser.add_argument("--sysfs-root", type=Path, default=DEFAULT_SYSFS_ROOT)
    parser.add_argument("--charger-helper", type=Path, default=DEFAULT_CHARGER_HELPER)
    parser.add_argument("--power-cycle", action="store_true", help="turn charger off, wait, then on")
    parser.add_argument("--charger-on-delay", type=float, default=10)
    parser.add_argument("--fingerbot-base-url", default=DEFAULT_FINGERBOT_BASE)
    parser.add_argument("--fingerbot-token-json", type=Path, default=DEFAULT_FINGERBOT_TOKEN_JSON)
    parser.add_argument("--fingerbot-angle-enum", default="2")
    parser.add_argument(
        "--fingerbot-press-ms",
        type=int,
        action="append",
        default=[],
        help="press the headset button for N ms before the SDP watch; may be repeated",
    )
    parser.add_argument(
        "--fingerbot-hold-during-charger-on-ms",
        type=int,
        help="with --power-cycle, start an N ms button hold before turning charger back on",
    )
    parser.add_argument(
        "--charger-on-during-hold-delay",
        type=float,
        default=2,
        help="seconds after hold starts before turning charger on",
    )
    parser.add_argument(
        "--operator-cue-countdown",
        type=float,
        default=3,
        help="seconds to pause after the TP10 cue before charger turn-on",
    )
    parser.add_argument("--skip-ums-watch", action="store_true")
    parser.add_argument(
        "--prestart-ums-watch",
        action="store_true",
        help="start UMS watcher immediately instead of after SDP detection",
    )
    parser.add_argument("--no-dump", dest="dump", action="store_false", default=True)
    parser.add_argument("--dump-max-bytes", type=parse_int)
    parser.add_argument("--no-carve", action="store_true")
    parser.add_argument("--no-triage", action="store_true")
    parser.add_argument("--no-boot-uboot", action="store_true")
    parser.add_argument(
        "--uboot-script",
        type=Path,
        action="append",
        help="U-Boot .uuu script to try after SDP detection; may be repeated",
    )
    parser.add_argument(
        "--try-default-uboot-matrix",
        action="store_true",
        help="try the prepared 9x9 and 14x14 autoums scripts in one SDP window",
    )
    args = parser.parse_args(argv)
    uboot_scripts = selected_uboot_scripts(args)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    out_dir.chmod(0o700)
    (ROOT / "evidence" / "latest_physical_sdp_window.txt").write_text(str(out_dir), encoding="utf-8")

    summary: dict[str, object] = {
        "started_utc": stamp(),
        "out_dir": str(out_dir),
        "sdp_detected": False,
        "commands": [],
        "charger_actions": [],
        "fingerbot_actions": [],
        "notes": [
            "No SSH authentication is attempted by this script.",
            "Human action required: briefly short TP10 to GND during USB attach/power-up.",
            "Fingerbot auth tokens are not written to summary JSON or redacted logs.",
        ],
    }
    summary["uboot_scripts"] = [str(script) for script in uboot_scripts]
    summary["preflight"] = preflight(out_dir, args.charger_helper, uboot_scripts, args.fingerbot_token_json)

    if args.power_cycle:
        perform_power_cycle(args, out_dir=out_dir, summary=summary)

    if args.fingerbot_press_ms:
        for press_ms in args.fingerbot_press_ms:
            summary["fingerbot_actions"].append(
                fingerbot_press(
                    base_url=args.fingerbot_base_url,
                    token_json=args.fingerbot_token_json,
                    press_ms=press_ms,
                    angle_enum=args.fingerbot_angle_enum,
                    out_dir=out_dir,
                )
            )

    ums_proc: subprocess.Popen[str] | None = None
    if args.prestart_ums_watch and not args.skip_ums_watch:
        ums_proc, ums_log = start_ums_watcher(args, out_dir)
        summary["ums_watch"] = {"pid": ums_proc.pid, "stdout": str(ums_log)}

    print("Physical window armed.", flush=True)
    print("Keep the TP10-to-GND short through USB attach/power-up until SDP appears or boot completes.", flush=True)

    deadline = time.monotonic() + args.duration
    events: list[dict[str, object]] = []
    detected: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        devices = find_sdp_devices(args.sysfs_root)
        events.append({"utc": stamp(), "devices": devices})
        if devices:
            detected = devices
            break
        time.sleep(args.poll_interval)

    summary["events"] = events
    summary["sdp_detected"] = bool(detected)
    summary["sdp_devices"] = detected

    if detected and ums_proc is None and not args.skip_ums_watch:
        ums_proc, ums_log = start_ums_watcher(args, out_dir)
        summary["ums_watch"] = {"pid": ums_proc.pid, "stdout": str(ums_log)}

    if detected and not args.no_triage:
        triage_dir = out_dir / f"sdp_triage_{stamp()}"
        summary["commands"].append(
            run_command(
                [
                    sys.executable,
                    str(ROOT / "tools" / "dreem_sdp_triage.py"),
                    "--no-wait",
                    "--out-dir",
                    str(triage_dir),
                ],
                cwd=ROOT,
                out=out_dir / "sdp_triage_stdout.log",
                timeout=180,
            )
        )

    if detected and not args.no_boot_uboot:
        uboot_result = boot_uboot_scripts(
            uboot_scripts,
            out_dir=out_dir,
            ums_proc=ums_proc,
            post_boot_wait=args.post_boot_wait,
        )
        summary["uboot_attempts"] = uboot_result["attempts"]
        summary["commands"].extend(
            attempt["command"] for attempt in uboot_result["attempts"] if "command" in attempt
        )
        if uboot_result.get("ums_summary"):
            summary["ums_summary"] = uboot_result["ums_summary"]

    if ums_proc is not None:
        summary["ums_watch_returncode"] = stop_process(ums_proc)
        summary.setdefault("ums_summary", wait_for_ums_summary(ums_proc, out_dir, 1))

    summary["finished_utc"] = stamp()
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary.get("ums_summary", {}).get("disk_detected"):
        return 0
    if summary["sdp_detected"]:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
