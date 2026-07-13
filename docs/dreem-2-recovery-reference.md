# Dreem 2 Raw Data Recovery Reference

Updated: 2026-07-06

This file is the consolidated handoff for the Dreem 2 raw-data recovery work. It preserves the durable facts, tested outcomes, operational constraints, and next steps another owner needs to continue the investigation.

Do not add credential values, tokens, passwords, Wi-Fi PSKs, cookies, Authorization headers, signed URLs, or reusable secret material. Use placeholders for device-specific identifiers and keep the documented conclusions reproducible on another owner's hardware.

## How To Use This File

Read this file in this order:

1. `Project Purpose`, `Hard Constraints`, and `Current Best Next Action` to understand the goal, stop rules, and only current high-value next move.
2. `Device Inventory`, `Hardware Facts`, and `Physical Recovery Attempts` before touching the board.
3. `BLE Surface`, `Backend And API Findings`, and `Android App, APK, Pixel, Auth` before trying software routes.
4. `Paths Not To Repeat`, `Viable Future Paths`, and `Open Questions` before planning new work.

## High-Level Conclusions

- The raw `.h5` target has not been recovered.
- Root/filesystem access has not been obtained.
- The normal BLE/app report path is understood and returns a compact `reporting_v2.data` ZIP, not raw EEG.
- The companion app stores and uploads that same compact report body; it does not secretly convert it into HDF5.
- Backend `reportv2` stores and returns compact reports; tested backend/config/content/dataupload routes did not expose raw files, firmware/rootfs, SSH credentials, or useful owner auth.
- D902 server URL validation rejects local/arbitrary hosts, and headset TLS appears blocked by device-side trust against the current production certificate chain.
- The LAN service surface is SSH only, but no credentials/exploit path was found and SSH brute force/user enumeration must not resume.
- The remaining practical path is physical recovery: reliable TP10-to-GND SDP entry followed by accepted boot/UMS/eMMC access, or professional eMCP extraction.

## Project Purpose

The project is to recover either:

- root/filesystem access to the user's own Dreem 2 headset, or
- the raw full-fidelity overnight Dreem recording file, expected to be HDF5 `.h5`.

The desired artifact is not the normal companion-app sleep report, not a live BLE preview stream, and not a derived hypnogram alone. The target is the stored raw recording with the original high-rate EEG and accompanying sensor data.

Current result:

```yaml
root_obtained: false
raw_h5_recovered: false
compact_ble_report_recovered: true
filesystem_access: false
ssh_access: false
owner_cloud_auth: false
local_upload_capture: not_seen
work_status: documented handoff; next action requires an operator-controlled hardware attempt
```

The main conclusion is that every software-visible path tested so far leads to compact processed reports, metadata, or low-rate live preview data. The strongest remaining path is physical i.MX6ULL recovery: force the SoC into Serial Downloader Protocol during USB attach/power-up, then use an accepted recovery path or direct storage technique to expose/dump eMMC.

## Hard Constraints

```yaml
objective: recover root or raw full-fidelity overnight Dreem 2 .h5 from the user's own headset
scope: user's own device and local LAN
do_not_mark_complete_until: root obtained or verified raw Dreem HDF5 recovered
```

Operational constraints:

- Do not run SSH brute force, password guessing, broad user enumeration, Hydra, Medusa, Ncrack, Patator, `sshpass`, `dropbear_user_enum.py`, or equivalent.
- Do not resume charger/fingerbot loops, Pixel automation, or repeated wake toggles without explicit current permission.
- Prefer one-shot checks with short timeouts and cleanup traps.
- Do not blindly fuzz or write unknown BLE characteristics.
- Do not casually trigger firmware-update characteristics such as `D706` without a valid package, recovery plan, and explicit approval.
- Do not repeat report/backend fetch loops that are known to return the same compact report.
- Do not print secret values, backend response bodies, auth tokens, passwords, Wi-Fi values, signed URLs, or credential files.

## Current Best Next Action

The only non-repeated path with a concrete chance is physical SDP/UMS recovery with a real human-applied TP10-to-GND short.

Run:

```bash
tools/dreem_physical_sdp_window.py --power-cycle --charger-on-delay 2 --fingerbot-hold-during-charger-on-ms 8000 --charger-on-during-hold-delay 2 --operator-cue-countdown 3 --duration 600 --poll-interval 0.25 --post-boot-wait 180 --try-default-uboot-matrix
```

Required human action:

- Apply and hold a direct TP10-to-GND short when cued.
- Keep the short through charger turn-on / USB attach / power-up.
- Hold until SDP appears or normal boot completes.

Why this is different from prior failed runs:

- Charger/fingerbot-only windows did not enumerate SDP.
- The runner was fixed so the TP10 short prompt is emitted before charger turn-on, not after.
- A 1 kOhm resistor was reported too gentle; the viable historical method was a direct short during the power/attach window.

Expected SDP USB ID:

```text
15a2:0080
```

If a block device appears through UMS, dump read-only and carve for HDF5 magic.

## Repository Layout

This repository is a focused Dreem 2 recovery archive.

```yaml
docs: current narrative, evidence summary, attempt history, references, and community draft
docs/evidence-summary.md: curated public evidence summary
tools: maintained recovery, BLE, SDP, UMS, and HDF5 carve helpers
recovery: imx_usb configs, UUU scripts, OpenOCD config, flashable U-Boot UMS payloads, and defconfigs to rebuild them
hardware: board photos, labeled test-point macros, and the FCC construction-photo exhibit
third-party/source-snapshots: Dreem-specific upstream reference code (DreemEEG, dreem-standalone)
```

Current active tool inventory:

```yaml
tools/dreem_physical_sdp_window.py: orchestrates power-cycle SDP watch, triage, U-Boot matrix, UMS watch
tools/dreem_sdp_recovery_watch.py: SDP USB recovery-device watcher
tools/dreem_sdp_triage.py: SDP triage helper
tools/dreem_sdp_checkdata.py: SDP read/check helper
tools/dreem_ums_dump_watch.py: watches/dumps newly exposed UMS block devices
tools/dreem_h5_carve.py: carves HDF5 signatures from dumps
tools/dreem_btclassic_report_fetch.py: Bluetooth Classic report fetch probe
tools/dreem_btclassic_request.py: Bluetooth Classic request helper
tools/dreem_btclassic_wifi_auth.py: Bluetooth Classic Wi-Fi auth helper
tools/dreem_att_client.c: raw ATT client experiment
```

Prepared U-Boot artifacts:

```yaml
recovery/u-boot/build-configs/u-boot-mx6ul-9x9-ums: LPDDR2-flavored path, considered more plausible
recovery/u-boot/build-configs/u-boot-mx6ul-14x14-ums: DDR3/14x14 fallback
recovery/u-boot/ums-boot-assets/boot_mx6ul_9x9_autoums.uuu: default UUU script used by the SDP runner
recovery/u-boot/ums-boot-assets/boot_mx6ul_14x14_autoums.uuu: fallback UUU script used by --try-default-uboot-matrix
recovery/ocram/uuu-probes/sdp_register_triage.uuu: non-persistent UUU SoC-register triage script
```

## Device Inventory

```yaml
dreem_headset:
  model: Dreem 2 / Dreem Two / Beacon
  fcc_id: 2AH2Q-DREEM2
  identifiers: discover the BLE address, Wi-Fi address, and IP for your own device
  firmware_observed:
    - 4.6.9 in one read-only BLE pass
    - 4.7.11+PRODUCTION in later/current backend and BLE evidence
  hardware_version: v2plus_medical
  ssh_banner_seen:
    - SSH-2.0-dropbear_2016.74
    - SSH-2.0-dropbear_2018.76
android_test_host:
  tested_device: rooted Pixel 7
  helper_app: com.codex.dreemble
optional_bench_automation:
  - operator-supplied smart-plug helper
  - operator-supplied Fingerbot API and token
  - webcam for observing the headset during timed boot attempts
```

## Hardware Facts

```yaml
main_board_marking: Femto MP-V2 / Femto MP-V2+
soc: NXP i.MX6ULL
soc_marking: MCIMX6Y1DVK05AB 1N70S
sdp_usb_id: 15a2:0080
storage_ram: Kingston 04EMCP04-NL2DM627
storage_interpretation: likely 4 GB eMMC + 4 Gb / 512 MB LPDDR2 eMCP
storage_package: eMMC 5.0 / HS200, 162-ball FBGA, about 11.5 x 13 x 1.0 mm
pmic: NXP/Freescale MC32PF3000A6
afe: ADS1294-class / TI 24-bit biopotential frontend
other_parts: WM8960 audio codec; 19.2 MHz oscillator on sensor/audio side
debug_pads_seen: TP2 TP3 TP7 TP8 TP9 TP10 TP11 TP21 TP32 TP38 TP39 plus unlabeled pads
likely_grounds: TP32, TP39
important_boot_pad: TP10 is the suspected SDP/eMMC-starve/control line
storage_access_note: eMCP is BGA, not clip-friendly
```

Board/photo conclusions:

- Storage-side local photos show i.MX6ULL above the Kingston eMCP on the `Femto MP-V2+` board.
- The CPU/eMCP/USB board and acquisition/analog board have different TP labels. Pad notes here refer to the CPU/eMCP/USB board unless explicitly stated otherwise.
- FCC photos clarify storage-side labels including TP2, TP7, TP9, TP10, TP11, TP32, and TP39.
- The acquisition/analog board has TP2, TP3, TP5, TP6, TP7, TP8, TP9, TP10, TP12, and TP13, but those are not the CPU/eMCP storage-side pads.
- No visible grouped eMMC service footprint was found for CLK/CMD/DAT0/DAT1/DAT2/DAT3.
- No confirmed reset/boot-mode/JTAG pad group has been identified.
- Non-chip-off eMMC reading is theoretically possible only with confirmed CLK/CMD/DAT0, power rails, and a way to keep the i.MX6 host inactive. Current photos and probing do not provide that.
- The high-confidence direct-storage path is professional eMCP/BGA removal and reading the eMMC portion with a compatible adapter/programmer.

Pad electrical observations:

| Pad | Later ohms-to-ground observation | USB-powered voltage |
| --- | --- | ---: |
| TP2 | Jumps around 60 kOhm to 250 kOhm | 4.33 V |
| TP3 | Starts around 300 kOhm and increases | 3.11 V |
| TP7 | Starts around 300 kOhm and increases | 4.28 V |
| TP8 | Starts around 100 kOhm and increases | 3.38 V |
| TP9 | Starts around 300 kOhm and increases | 3.28 V |
| TP10 | Starts around 400 kOhm and increases | 1.81 V |
| TP11 | Starts around 400 kOhm and increases | 0.003 V |
| TP32 | About 0.6 ohm | likely ground |
| TP38 | Starts around 300 kOhm and increases | 3.14 V |
| TP39 | About 0.5 ohm | likely ground |

Additional unlabeled readings:

- Two unlabeled pads near TP8: left around 3.1 V, right 0 V.
- Two unlabeled pads underneath/top near the vendor-date area: both around 3.1 V.
- One unlabeled board-edge pad: no beep, around 300 kOhm and rising.
- One probed pad caused the LED to turn green during probing, unlike others, but was not conclusively identified.

## Physical Recovery Attempts

### UART / Logic Analyzer

Tools used:

- Tigard V1.1 FT2232H.
- LA1010 logic analyzer.
- Multimeter.
- sigrok/PulseView.
- UART scan scripts across saved `.sr` files.

Results:

- Early UART tests are weak evidence because some lacked shared ground.
- Later common-ground captures still did not produce readable boot logs.
- Later evidence points to a 3.3 V logic rail, not 1.8 V.
- Captures showed silence, noisy garbage, or isolated power-state transitions.
- A scan across 34 sigrok `.sr` captures found only noisy inverted high-baud candidates around 1.5-2.0 Mbaud.
- No credible strings such as U-Boot, Linux, Freescale, i.MX, login prompts, or shell output were found.

Important capture observations:

| Pad/net | Observation | Interpretation |
| --- | --- | --- |
| TP3 boot capture | 5 MS/s, 15 s, all channels high, zero transitions | No UART-looking activity |
| TP11 boot capture | 5 MS/s, 15 s, one channel had 1-18 transitions, others high | Not readable UART |
| TP2 boot capture | 5 MS/s, 15 s, one channel had 14,458 transitions and about 99.6% high | Activity exists but no valid UART decode |
| TP8 boot capture | 13.6 s usable, one transition, about 76.5% high | Not UART console |
| TP9 boot capture | 15 s, 3 transitions, 85-87% high | Not UART console |
| TP10 boot capture | 15 s, 2 transitions, about 34% high | Strap/control-ish candidate, not chatty UART |
| TP38 boot capture | 15 s, one transition, about 76% high | Not UART console |
| `current_uart_pin_level` | 2 MS/s, all channels high, zero transitions | Idle-high possible, no boot text |
| `vd1` | Inverted high-baud decoder produced noisy candidates, no keywords | Likely not console or not decoded |
| `u8left` / `u8right` | Some activity, no valid UART candidates | Possibly unrelated digital activity |

Conclusion: no usable UART/root console was found. Possible explanations are wrong pad, disabled console, missed timing, or console on another interface.

### SDP / U-Boot / USB Mass Storage

What is known:

- The i.MX6ULL ROM SDP path is real.
- Expected USB ID is `15a2:0080`.
- Manual/direct TP10-to-GND short during power-up reportedly produced SDP behavior historically.
- A 1 kOhm resistor was too gentle.
- Polling `/sys/bus/usb` idVendor/idProduct is more reliable than eyeballing `lsusb`.
- `imx_usb` readback in SDP reported HAB security state as production mode.

Prepared tools and payloads:

- `uuu`, `imx_usb`, OpenOCD, `h5ls`, `binwalk`, `flashrom`, `sigrok-cli`, CST/SRK tooling.
- U-Boot UMS payloads for i.MX6UL EVK assumptions:
  - `mx6ul_9x9_evk_defconfig` / LPDDR2 path looked more plausible.
  - `mx6ull_14x14_evk` / DDR3 path prepared as fallback.
- A physical SDP watcher that watches for `15a2:0080`, runs triage, tries U-Boot UMS scripts, watches for USB mass storage, dumps a new USB disk read-only, and carves HDF5 signatures.

Observed behavior:

- Plain power/button timing did not enumerate SDP.
- Charger/fingerbot-only windows did not enumerate SDP.
- No USB mass storage device appeared.
- One SPL attempt appeared to load from the tool's perspective:
  - SPL size: 39,936 bytes.
  - IVT header: `0x00907400`.
  - Entry point: `0x00908000`.
  - Jump target: `0x00907400`.
- After SPL jump there was still no useful UART, U-Boot prompt, re-enumeration, UMS gadget, or block device.
- OCRAM load testing once failed with `report 2 out err=-7`.
- UUU OCRAM test saw a fresh SDP device but failed due to local script/path issue before proving execution.
- IOMUX/USDHC and fuse/register reads were possible over SDP, so ROM/debug reads worked at least partially.

Likely blockers:

- Physical short timing not achieved during automated runs.
- HAB/secure boot blocks unsigned code.
- SPL starts but DRAM init fails.
- Console/USB path is wrong even if code starts.

Latest runner fix:

- `tools/dreem_physical_sdp_window.py` was fixed so `--power-cycle` prints/records "Apply and hold the TP10-to-GND short now; charger turn-on follows." before charger turn-on.
- Default `--operator-cue-countdown` is 3 seconds.
- The final armed message now tells the operator to keep the short through USB attach/power-up until SDP appears or boot completes.
- The cue ordering and power-cycle behavior are covered by `tests/test_dreem_physical_sdp_window.py`.

### JTAG / eMMC / Chip-Off

Status:

- No confirmed JTAG session.
- Pad/photo review did not identify a confident JTAG group.
- Direct eMMC/chip-off considered viable but invasive because storage is BGA eMCP.
- No separate SPI NOR was proven to hold desired data.
- Bus Pirate 6 and Tigard remain useful for future probing, but no direct storage dump has happened.

Conclusion: eMCP/BGA chip-off or formal board-level mapping remains a fallback if SDP/HAB cannot be solved.

## Power, Charger, LED, Webcam, Fingerbot

Observed LED/power behavior:

```yaml
solid_blue: charging mode or connected state; not the preferred BLE provisioning state
flashing_blue_off_charger: useful awake/advertising state
single_press_while_flashing_blue: no visible effect observed
long_press_while_flashing_blue_off_charger: powers headset off
8_second_fingerbot_press: powered headset off, not a wake action
charger_off: best for BLE/server/Wi-Fi provisioning
charger_on: best for Wi-Fi/upload wake after provisioning
```

Webcam:

- Logitech BRIO path works with `sudo ffmpeg` after warm-up.
- Direct user access to `/dev/video0` was denied by root:video permissions in the source environment.
- Initial frame may be black; delayed frame can work.
- Current framing did not clearly show headset LED, so aim/lighting should be adjusted before relying on visual state evidence.

Fingerbot / GLKVM facts:

```yaml
base: operator-supplied GLKVM URL
cert_handling: PowerShell needs SkipCertificateCheck
auth_endpoint: POST /api/auth/login with operator-configured credentials
read_only_endpoints:
  - /api/fingerbot/battery
  - /api/fingerbot/local_version
read_only_verified:
  battery: 100
  firmware: 1.1.0
press_endpoint: /api/fingerbot/click with auth_token query param, press_time ms, angle_enum strength
verified_press: press_time=250 angle_enum=2 returned success
failed_press: press_time=500 returned BadRequestError Failed to click in one pass
strengths: angle_enum=1 light, angle_enum=2 firm
fingerbot_ble_service: 63630001-39fe-48d0-b1d8-d18d647d5fa9
fingerbot_ble_characteristic: 63630002-39fe-48d0-b1d8-d18d647d5fa9 READ/WRITE/NOTIFY
safety: API details are reference only; do not call without explicit current permission
```

## BLE Surface

Pixel helper app was used for most BLE reads/writes/notifications because host BlueZ behavior was flaky. Bench-host BlueZ pairing/bonding was also used for GATT inventories.

Known characteristic roles:

| Characteristic | Role/result |
| --- | --- |
| D003 | Diagnostic JSON-ish payload, not data export |
| D007 | READ/WRITE but passive read returned status 2 / no payload |
| D008 | READ/WRITE but passive read returned status 2 / no payload |
| D102 | Wi-Fi config write path; encrypted/framed JSON |
| D103 | Wi-Fi config/status read |
| D203 | Battery level |
| D204 | Plugged status |
| D208 | Health/error status |
| D301 | Live preview notifications |
| D302 | Record command; `3` starts nap, `0` finalizes/stops |
| D304 | Record status |
| D309 | Current record UUID/status |
| D30A | Nap config JSON write before start |
| D401 | Latest report UUID |
| D402 | Latest report bytes; compact ZIP with `reporting_v2.data` |
| D601 | Set time |
| D701 | Root firmware version read |
| D702 | App compatibility read |
| D704 | Firmware status notify |
| D705 | Real firmware version read |
| D706 | Set mobile version / firmware flow write; do not loop casually |
| D707 | Firmware update start write |
| D708/D709 | Version/hardware reads; D709 hardware version |
| D901 | User ID write |
| D902 | Server URL config write |
| D903 | Headband MAC read |
| D904 | Server password required/status read |
| D905 | Server password write |
| D951/D952 | Pharma report data/UUID in Alfin; absent on this headset/firmware |

Historical value handles:

```yaml
D905_server_password: 0x003d
D902_server_urls: 0x0043
D901_user_id: 0x0045
D402_latest_report_data: 0x0075
D401_latest_report_uuid: 0x0077
D309_record_uuid_or_status: 0x0085
D301_live_preview_notify: 0x0095
D301_cccd: 0x0096
```

Read-only GATT findings:

- Official app-visible surface exposes setup/config/status, live low-rate EEG display samples, record control, and compact derived reports.
- Exhaustive safe/readable sweep found diagnostics, audio/content state, alarm/relax config, and status values.
- No raw stored `.h5`, raw bulk EEG recording, file browser, eMMC command, or unencrypted upload body was exposed.

Additional safe-read examples:

```yaml
D003: diagnostic JSON prefix with push/dock/adc/i2c/stc/temp/ads/pulse fields
D509: audio/content downloaded_content list
D805: alarm config payload `{}`
D803: 20 zero bytes
D852: small binary status payload
DA03: status 2, no relax report payload
DA05: status 6, no payload
```

BLE problem observed later:

- Pixel BLE often connected but service discovery returned empty lists, timeouts, status 133, or disconnect status 22.
- Helper was patched to retry empty services and bond failures, but post-rebond still failed in some cases.
- Old local/remote automation sometimes stole first GATT windows; killed/disabled before future attempts.

## BLE Recording And Report Path

What works:

```yaml
start_recording: write D30A setNapConf, then D302=3
stop_finalize: D302=0
wrong_stop_command: D302=2; status may look successful but does not finalize
```

Observed fresh-nap result:

```yaml
zip_entry: reporting_v2.data
report_size: 402 bytes
```

Conclusion:

- `D401`/`D402` is the official compact report path.
- Classic/RFCOMM IDs `601`/`602` point to the same compact report surface.
- The compact report contains `reporting_v2.data`, not HDF5 magic and not high-rate EEG.
- The app stores/uploads those exact compact bytes; it does not transform them into raw HDF5.
- Repeating `D402` or Classic `602` pulls is not useful without new protocol evidence.

## BLE Live Preview

`D301` notifications work as a live/preview route:

```yaml
packets: 484
bytes: 13552
duration: 20 seconds
decode: four little-endian floats per notification, low preview/display rate
```

Conclusion: useful smoke test and live preview, but not the stored overnight raw file.

## BLE Wi-Fi And Server Config

Wi-Fi (`D102`):

- Format is app-encrypted length-prefixed JSON.
- Works best with charger off and headset awake/advertising.
- Good state reads as `wifiStatusLE=0`.
- Plugged/charging writes can return BLE status 0 while device internally records `wifiStatusLE=9` and clears `last_ssid`.

Reliable sequence:

```yaml
1: charger off
2: wake/advertise
3: restore D901/D902/D905
4: verify D904 is 00 00 00 00
5: write framed Wi-Fi D102
6: verify wifiStatusLE=0
7: turn charger on for Wi-Fi/upload wake without rewriting Wi-Fi while plugged
```

Server/user/password:

```yaml
D901_user_id: accepts UUID-shaped values
D902_server_urls:
  format: 4-byte little-endian JSON length + Jackson JSON fields user_api_url,user_auth_url
  accepted: https://login.rythm.co and https://api.rythm.co/v1/dreem
  rejected_status_3:
    - local IP HTTPS
    - local HTTP/HTTPS targets
    - https://example.com
    - parser tricks such as login.rythm.co@example.com
    - suffix tricks such as login.rythm.co.example.com
    - official hostnames over plain HTTP
D905_server_password: accepts writes
D904_server_password_required: clears to 00 00 00 00 after valid D905 write
```

Important bug found:

- Some scripts parsed `hawk_plain.tsv` incorrectly and wrote column 2 for `CURRENT_DREEMER_UUID`, which was the value type `java.lang.String`, not the UUID.
- Correct parser uses column 3 and strips quotes.
- Bad D901 value explains some status 3 writes.

Conclusion:

- Wi-Fi and server config are controllable enough for state restoration.
- D902 server URL redirection to a local listener is effectively blocked by URL validation.
- D905 password write clears local server-password state but does not by itself unlock raw upload or SSH.

## Network, TLS, Upload, And MITM

LAN surface:

```yaml
headset_ip_when_online: discover from the access point's DHCP or neighbor table
open_tcp_ports: only 22/tcp
ssh_banner_currentish: Dropbear 2018.76
older_banner_seen: Dropbear 2016.74
auth_methods: publickey,password
```

SSH result:

- None-auth rejected.
- Saved/backend/generated/headband secret candidates failed against plausible users.
- User timing and malformed-public-key enum probes produced no useful signal.
- Public Dropbear research did not identify a practical no-auth root path for observed versions.
- SSH brute force/auth guessing/user enumeration is now explicitly stopped and must not resume.

Network upload findings:

- Headset can join Wi-Fi.
- Charger-on wake can produce DHCP/ARP and production DNS/TLS attempts.
- Charger-off is better for BLE provisioning but may show little/no upload network traffic.
- AP/bench-host passive captures are incomplete if the bench-host is not AP/router mirror.
- No large raw-data upload body was observed.
- `reportv2` after upload triggers remained empty or returned compact reports only.

UDM/static route facts:

```yaml
udm_api_usable: true, through token stored on the bench host
udm_ssh: root/ubnt/admin attempts failed; API was enough
route_endpoint: POST /proxy/network/api/s/default/rest/routing
working_route_type: static-route with static-route_network, static-route_nexthop, static-route_distance, gateway_type
production_ips_observed:
  - 18.157.241.11
  - 3.124.82.78
  - 52.29.32.122
```

MITM/tunnel conclusions:

- D902 accepts only production-style Rythm URLs.
- Route MITM to a local self-signed TLS sink caught ClientHello but the headset reset after certificate response.
- Transparent tunnel to the real production TLS endpoint showed:
  - SNI `login.rythm.co`.
  - ClientHello length 517 bytes.
  - Server response about 4528 bytes.
  - TLS 1.2 selected.
  - Cipher `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`.
  - Headset sent no Finished/client key exchange/application request after server certificate and closed after about 60 seconds.
- Therefore the blocker is not merely TLS version/cipher; likely the old headband trust store cannot validate the current 2026 Let's Encrypt chain.

Observed production chain:

```yaml
host: login.rythm.co / api.rythm.co
leaf: login.rythm.co or api.rythm.co
issuer_chain: Let's Encrypt YR2 / YR1 -> ISRG Root YR -> ISRG Root X1
example_validity_window_seen: 2026-06-09 to 2026-09-07
```

Conclusion: without root/filesystem access, a valid public certificate/private key for production hostnames, a signed firmware/update route, or a device trust-store bypass, network MITM cannot reveal the encrypted upload body.

## Backend And API Findings

Legacy backend still responds in several areas:

- Disposable guest account creation works.
- Token issuance for dummy guests works.
- The headband resolver accepted the headset's Wi-Fi MAC in uppercase underscore form and returned its backend headband ID.
- Colon/lowercase/BLE MAC variants failed for that resolver.
- Configuration by resolved ID returns firmware/content/storage/nickname metadata.
- Content endpoints expose audio/UI content metadata, not firmware/rootfs/raw EEG.
- Direct S3 bucket listing and unsigned object fetches returned access denied.

Important endpoint shapes:

```yaml
headband_resolver: /v1/dreem/dreemer/dreemer/{dreemer_id}/headband/?address={WIFI_MAC_WITH_UNDERSCORES}
configuration_by_id: /v1/dreem/headband/configuration/{headband_id}/
content_details: /v1/dreem/headband/content_set/content_details/?headband=...
update_password: POST /v1/dreem/headband/headband/update_password/
installed: POST /v1/dreem/headband/headband/{id}/installed/
nightreport_list: GET /v1/dreem/nightreport/reportv2?user=<dreemer>&since=<seconds>
nightreport_detail: GET /v1/dreem/nightreport/reportv2/{record}
nightreport_upload: POST /v1/dreem/nightreport/reportv2 multipart fields user,device,record,start,end,report
dataupload_status: GET /v1/dreem/dataupload/data/{record_id}/status
```

Headband configuration exposes:

- firmware version.
- content IDs and downloaded content count.
- storage counters.
- nickname.

It does not expose:

- raw reports.
- SSH credentials.
- server password.
- root filesystem.
- firmware/rootfs download URL.

Backend update password:

```yaml
before_allotment: 403
after_post_allotment: 200 with a 20-character server-password value
BLE_D905: password works to clear D904
SSH: same password failed for root/admin/dreem/rythm and other tested candidates
```

`reportv2` semantics:

- Manual upload of the compact BLE `D402` 402-byte ZIP returned HTTP 201.
- The backend then listed and downloaded the exact same SHA-256.
- Download contained only `reporting_v2.data`.
- This proves `reportv2` stores compact app report bytes and does not transform or reveal hidden raw `.h5`.

Read-only route sweeps:

- API root resources included batch, configuration, content, content_set, firmware, headband, metrics, settings, systemlog, and others.
- Most returned 403/404/405/400 for disposable tokens.
- Raw/records/HDF5 guesses did not expose files.
- `OPTIONS` showed route shapes but no raw download path.

App-JWT / owner-ish probes:

- Hawk decryption recovered identifiers but not bearer/JWT tokens.
- Backend ownership enforcement blocked report lists for the real/app dreemer UUID.
- Direct checks of UUIDs from `BLACKLIST_RECORDS` returned 401 unauthenticated or 404 with dummy bearer.
- Additional app-JWT, algorythm, H5 endpoint, Wearipedia-shaped, and JWT-forgery probes did not reveal raw `.h5` access.

## Android App, APK, Pixel, Auth

Packages:

```yaml
patched_debuggable_app: co.rythm.dreem2
production_app_tested: co.rythm.dreem
helper_app: com.codex.dreemble
google_auth_helper: com.codex.dreemauth
alfin_app: com.dreem.alfin version 1.12.10
```

APK/static findings:

- D902 format is 4-byte little-endian JSON length followed by JSON fields `user_api_url` and `user_auth_url`.
- Protected payload constants/AES key/IV literals were found and used by helper/app.
- `headband/update_password` route returns a password that the app writes to D905.
- Firmware/audio update BLE paths exist, but APKs did not contain firmware blobs, rootfs images, CA bundles, or obvious trust overrides.
- Firmware update appears backend/headset-driven, not APK-embedded.
- App report code uses D401/D402, parses `reporting_v2.data`, stores the compact body under app files, then uploads that same body to `reportv2`.

Patched app state:

```yaml
package: co.rythm.dreem2
debuggable: true
run_as_pull: works
Dreem_db_present: true
NightReport_rows: 0
raw_h5_or_large_artifact: none found
bearer_or_jwt: none found
```

Hawk/Conceal:

```yaml
decode_works_with_crypto_KEY_256: true
decrypted_key_count: 26
CURRENT_DREEMER_UUID: present
REFRESH_TOKEN: Boolean true flag, not token string
CURRENT_AUTH_TOKEN: absent
CURRENT_JWT_TOKEN: absent
CURRENT_GOOGLE_TOKEN: absent
CURRENT_LOGIN_METHOD: absent
BLACKLIST_RECORDS: 2 UUIDs; direct reportv2 checks did not expose files
```

Production app / Google auth:

- Patched app cannot complete Google OAuth because package/signature is not registered.
- Production app likely has the registered Google package/signature but is not debuggable, has `allowBackup=false`, and cannot coexist with patched app due `co.rythm.fileprovider` provider conflict.
- One production-app flow produced a Google token, but Rythm login/API probes returned 404/401 and did not produce a usable Rythm bearer/JWT or raw-data access.
- Launching current official app did not repopulate auth; it hit first-run/crash paths.

Alfin:

- Alfin 1.12.10 still points to `https://login.rythm.co/` and `https://api.rythm.co/v1/dreem/`.
- It uses the same compact D401/D402 report path.
- It adds optional pharma report characteristics D951/D952 and `pharma_report.data`, but those characteristics were absent on this headset/firmware.
- No embedded firmware, `.h5`, trust-store override, CA bundle, or pinning bypass was found.

Conclusion: app/APK/Pixel routes did not expose raw files, useful owner auth, firmware/rootfs, or a hidden raw transfer path.

To reproduce the application analysis, obtain the relevant APKs through a lawful source. The versions examined were Alfin 1.12.10, Dreem Connect 1.0.4, and Dreem 2 version 2.15.1/build 478. APKs are not required for the included Android helper projects.

## Public References And Community Material

Checked references include:

- FCC/internal photos for Dreem 2: `https://fccid.io/2AH2Q-DREEM2`
- MajorInput teardown: `https://www.majorinput.co.uk/post/a-closer-look-at-the-dreem-eeg-headband`
- Dreem support docs for store-and-forward Wi-Fi behavior.
- DreemEEG live BLE prior art.
- Dreem-Organization public GitHub repos.
- Dreamento / Wearipedia downstream tooling.
- Alfin app references.
- i.MX/U-Boot/imx_usb_loader/usbarmory references.

The public links are tracked in `references.md`, and the small snapshots used directly by this work are documented under `third-party/`.

Findings:

- DreemEEG and similar projects are live/low-rate BLE prior art, not stored `.h5` extraction.
- Dreem-Organization and research repos are useful after raw data exists, but did not contain device extraction code.
- `dreem-standalone` is infrastructure scaffolding for services such as algorythm, dataupload, headband, nightreport, and record; it does not include production service implementations.
- `dosed` and `dreem-learning-open` contain HDF5 tooling/schema examples, not acquisition paths.
- No public firmware/rootfs, SSH credential, trust-store material, or raw transfer protocol was found.

## Paths Not To Repeat

Do not spend more time on these without new evidence:

- Pulling BLE `D402` or Classic `602` expecting raw `.h5`.
- Re-fetching the same `reportv2` signed download.
- D905-only password write followed by the same AP capture/reportv2/dataupload checks.
- Plain power/button/charger/fingerbot SDP attempts without physically shorting TP10 to GND.
- D007/D008 passive reads.
- Blind BLE fuzzing or writes to unknown characteristics.
- D706 firmware trigger loops without firmware bytes and a recovery plan.
- App firmware URL greps or direct S3 fetches without a newly discovered signed URL.
- Backend content/config route sweeps without a new token/account state or endpoint clue.
- Local D902 rewrite attempts unless a new accepted server URL format or trust-store bypass is found.
- Charger-on Wi-Fi rewrites; do Wi-Fi/server provisioning charger-off, then turn charger on.
- SSH brute force, broad password guessing, user enumeration, Hydra, Medusa, Ncrack, Patator, `sshpass`, `dropbear_user_enum.py`, or equivalent.

## Viable Future Paths

Most plausible remaining paths:

1. Physical i.MX6ULL SDP entry with direct TP10-to-GND short during USB attach/power-up.
2. If SDP entry is reliable, solve HAB/secure boot, SPL/DRAM init, or an accepted recovery route that exposes eMMC.
3. Professional eMCP/BGA storage read or confirmed in-circuit eMMC tap with host isolation.
4. A firmware/rootfs image from another source that reveals credentials, uploader behavior, trust store, or update acceptance rules.
5. A valid old/current owner auth session that exposes additional owner-gated report/raw endpoints.
6. A real device trust-store/update path, valid certificate/private key path, or signed firmware/update mechanism that lets the headband complete HTTPS upload to a controllable endpoint.
7. A new BLE characteristic or protocol command not present in the documented GATT map and not found in exhaustive service discovery.

## Open Questions

These are the useful questions to take to other Dreem 2 owners/researchers:

1. Has anyone reliably entered i.MX6ULL SDP on Dreem 2 and confirmed TP10-to-GND timing?
2. Has anyone run signed or accepted code through Dreem 2 SDP, or confirmed HAB/secure boot behavior?
3. Does anyone have a known-good U-Boot/SPL config for this exact i.MX6ULL plus Kingston LPDDR2/eMCP package?
4. Has anyone identified JTAG pads or achieved OpenOCD on the Femto MP-V2 board?
5. Has anyone dumped the Dreem 2 eMCP/eMMC and identified where raw recordings live?
6. Does `reporting_v2.data` ever reference a raw object elsewhere, or is it purely the processed report?
7. Are there BLE characteristics beyond the `Dxxx` app-visible config/status/report surface that expose raw chunks?
8. Is there a known legacy TLS/root-CA problem with current Rythm production servers, and can it be worked around without root?
9. Does an authenticated original owner account expose raw-data endpoints not visible from disposable/current test accounts?
10. Has anyone seen firmware update packages for `4.7.11+PRODUCTION` or Dreem 2 Medical that can be analyzed?

## Bottom Line

No raw `.h5` has been recovered and no root shell has been obtained. BLE, app, backend, and network routes have been narrowed enough to treat them as spent unless new evidence appears. The compact app report path is well understood and is not raw EEG. The remaining high-value work is physical: make SDP entry reliable with a real TP10-to-GND short, then solve execution/UMS/eMMC access, or use professional direct-storage recovery.
