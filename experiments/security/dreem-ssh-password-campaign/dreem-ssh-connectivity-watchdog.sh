#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"

SERIAL="${SERIAL:-REDACTED-SERIAL}"
BLE_MAC="${BLE_MAC:-AA:BB:CC:DD:EE:50}"
WIFI_MAC_LC="${WIFI_MAC_LC:-aa:bb:cc:dd:ee:4f}"
TARGET_IP_FALLBACK="${TARGET_IP_FALLBACK:-192.0.2.148}"
HOST_PORT="${HOST_PORT:-2223}"
PIXEL_PORT="${PIXEL_PORT:-2223}"
BASE="${BASE:-$REPO_ROOT/evidence/dreem-ssh-password-campaign}"
SECRET_FILE="${SECRET_FILE:-$BASE/pixel-hotspot.secret}"
LOG="${LOG:-$BASE/ssh_password_campaigns/dreem-ssh-connectivity-watchdog.log}"
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"
RUN_SECONDS="${RUN_SECONDS:-108000}"
BLE_KEEPALIVE_SECONDS="${BLE_KEEPALIVE_SECONDS:-45}"
BRIDGE_CHECK_SECONDS="${BRIDGE_CHECK_SECONDS:-60}"

mkdir -p "$(dirname "$LOG")"

now_utc() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

log() {
  printf '%s %s\n' "$(now_utc)" "$*" >>"$LOG"
}

adb_cmd() {
  sudo adb -s "$SERIAL" "$@" </dev/null
}

pixel_su() {
  adb_cmd shell su -c "$1"
}

local_banner_ok() {
  python3 - "$HOST_PORT" <<'PY'
import socket
import sys

port = int(sys.argv[1])
s = socket.socket()
s.settimeout(3)
try:
    s.connect(("127.0.0.1", port))
    banner = s.recv(32)
    raise SystemExit(0 if banner.startswith(b"SSH-") else 1)
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

current_target_ip() {
  local ip
  ip="$(pixel_su "ip neigh show dev wlan2 2>/dev/null | awk '/$WIFI_MAC_LC/ {print \$1; exit}'" 2>/dev/null | tr -d '\r' | tail -n 1)"
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf '%s\n' "$ip"
  else
    printf '%s\n' "$TARGET_IP_FALLBACK"
  fi
}

target_ssh_ok() {
  local ip="$1"
  local status
  status="$(pixel_su "toybox nc -zvw 2 $ip 22 >/dev/null 2>&1; echo \$?" 2>/dev/null | tr -d '\r' | tail -n 1)"
  [[ "$status" == "0" ]]
}

start_softap() {
  local cmd
  cmd="$(python3 - "$SECRET_FILE" <<'PY'
from pathlib import Path
import shlex
import sys

kv = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        kv[k] = v
ssid = kv["SSID"]
password = kv["PASSWORD"]
print("cmd wifi start-softap " + shlex.quote(ssid) + " wpa2 " + shlex.quote(password) + " -b 2 -f 2412")
PY
)"
  pixel_su "cmd wifi stop-softap >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  sleep 2
  pixel_su "$cmd" >/dev/null 2>&1 || true
}

ensure_softap() {
  if pixel_su "ip -br addr show wlan2 2>/dev/null | grep -q UP" >/dev/null 2>&1; then
    return 0
  fi
  log "softap_missing restart"
  start_softap
}

write_wifi_config() {
  local cmd
  cmd="$(python3 - "$SECRET_FILE" "$BLE_MAC" <<'PY'
from pathlib import Path
import shlex
import sys

kv = {}
for line in Path(sys.argv[1]).read_text(errors="ignore").splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        kv[k] = v
args = [
    "am", "start", "-S", "-n", "com.codex.dreemble/.MainActivity",
    "--es", "address", sys.argv[2],
    "--ez", "wifiOnly", "true",
    "--ez", "configureWifi", "true",
    "--ez", "readOnly", "false",
    "--ez", "createBond", "false",
    "--ez", "removeBondFirst", "false",
    "--es", "wifiPayloadFormat", "framed",
    "--es", "ssid", kv["SSID"],
    "--es", "password", kv["PASSWORD"],
    "--ei", "security", "2",
    "--el", "directConnectDelayMillis", "7000",
    "--el", "operationGapMillis", "500",
    "--ei", "maxRetries", "1",
]
print(" ".join(shlex.quote(a) for a in args))
PY
)"
  adb_cmd shell am force-stop com.codex.dreemble >/dev/null 2>&1 || true
  adb_cmd shell "$cmd" >/dev/null 2>&1 || true
}

ble_time_keepalive() {
  adb_cmd shell am force-stop com.codex.dreemble >/dev/null 2>&1 || true
  adb_cmd shell am start -S -n com.codex.dreemble/.MainActivity \
    --es address "$BLE_MAC" \
    --ez timeOnly true \
    --ez readOnly false \
    --ez createBond false \
    --ez removeBondFirst false \
    --el directConnectDelayMillis 2500 \
    --el operationGapMillis 100 \
    --ei maxRetries 1 >/dev/null 2>&1 || true
}

start_bridge() {
  local ip="$1"
  adb_cmd forward --remove "tcp:$HOST_PORT" >/dev/null 2>&1 || true
  pixel_su "pkill -f 'toybox [n]c -L -p $PIXEL_PORT' >/dev/null 2>&1 || true; pkill -f '[n]c -L -p $PIXEL_PORT' >/dev/null 2>&1 || true; nohup toybox nc -L -p $PIXEL_PORT toybox nc $ip 22 >/data/local/tmp/dreem-ssh-bridge-$PIXEL_PORT.log 2>&1 &" >/dev/null 2>&1 || true
  sleep 1
  adb_cmd forward "tcp:$HOST_PORT" "tcp:$PIXEL_PORT" >/dev/null 2>&1 || true
}

repair_path() {
  local ip
  log "repair_start"
  ensure_softap
  write_wifi_config
  for _ in $(seq 1 75); do
    sleep 1
    ip="$(current_target_ip)"
    if target_ssh_ok "$ip"; then
      start_bridge "$ip"
      if local_banner_ok; then
        log "repair_ok ip=$ip host_port=$HOST_PORT"
        return 0
      fi
    fi
  done
  log "repair_failed"
  return 1
}

main() {
  local start now last_healthy last_ble_keepalive last_bridge_check ip campaign_pid
  start="$(date +%s)"
  last_healthy=0
  last_ble_keepalive=0
  last_bridge_check=0
  log "watchdog_start host_port=$HOST_PORT pixel_port=$PIXEL_PORT sleep_seconds=$SLEEP_SECONDS ble_keepalive_seconds=$BLE_KEEPALIVE_SECONDS bridge_check_seconds=$BRIDGE_CHECK_SECONDS"
  while true; do
    now="$(date +%s)"
    if (( now - start >= RUN_SECONDS )); then
      log "watchdog_stop reason=run_seconds"
      return 0
    fi

    campaign_pid="$(cat "$BASE/ssh_campaigns/current.pid" 2>/dev/null || true)"
    if [[ -n "$campaign_pid" ]] && ! ps -p "$campaign_pid" >/dev/null 2>&1; then
      log "campaign_not_running pid=$campaign_pid"
    fi

    ip="$(current_target_ip)"
    if target_ssh_ok "$ip"; then
      if (( now - last_bridge_check >= BRIDGE_CHECK_SECONDS )); then
        if ! local_banner_ok; then
          log "bridge_missing ip=$ip restart_bridge"
          start_bridge "$ip"
        fi
        last_bridge_check="$now"
      fi
      if (( now - last_healthy >= 300 )); then
        log "healthy ip=$ip"
        last_healthy="$now"
      fi
      if (( now - last_ble_keepalive >= BLE_KEEPALIVE_SECONDS )); then
        log "ble_time_keepalive"
        ble_time_keepalive
        last_ble_keepalive="$now"
      fi
    else
      repair_path || true
      last_healthy=0
      last_ble_keepalive=0
      last_bridge_check=0
    fi
    sleep "$SLEEP_SECONDS"
  done
}

main "$@"
