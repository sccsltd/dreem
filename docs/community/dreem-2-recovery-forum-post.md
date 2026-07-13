# Dreem 2 Raw Data / Root Recovery Attempts So Far

Updated: 2026-07-06

This is a human-readable summary of a long attempt to recover either root access or the raw overnight `.h5` data file from my own Dreem 2 headset. I am posting this so other Dreem owners/researchers can avoid repeating dead ends and maybe suggest new paths.

Current result: no root shell and no raw `.h5` recovered yet.

The strongest remaining path appears to be physical i.MX6ULL recovery: force the SoC into Serial Downloader Protocol (SDP) during USB attach/power-up, then try to expose or dump eMMC. Software-visible paths so far have only produced compact processed reports, not raw EEG/HDF5 files.

## Device And Hardware Context

Observed device:
- Dreem 2 / Dreem Two / Beacon.
- Firmware observed: `4.7.11+PRODUCTION`.
- Hardware version observed over BLE: `v2plus_medical`.
- Main board marking: `Femto MP-V2`.
- SoC: NXP i.MX6ULL, marking `MCIMX6Y1DVK05AB 1N70S`.
- Storage/RAM package: Kingston `04EMCP04-NL2DM627`, likely 4 GB eMMC plus 512 MB LPDDR2 eMCP.
- AFE appears ADS1294-class / TI 24-bit biopotential frontend.
- Other visible components include WM8960 audio codec and a 19.2 MHz oscillator on the sensor/audio side.
- USB SDP ID when in i.MX ROM downloader mode should be `15a2:0080`.
- Debug/test pads seen include TP2, TP3, TP7, TP8, TP9, TP10, TP11, TP21, TP32, TP38, TP39, plus unlabeled pads.
- TP32/TP39 looked like likely grounds.
- TP10-to-GND is the important suspected boot/SDP entry manipulation.
- Storage is BGA eMCP, so a casual clip-on dump is not realistic.
- The CPU/eMCP/USB board and the acquisition/analog board have different TP labels; the pad notes below refer to the CPU/eMCP/USB board unless explicitly stated otherwise.

Expected data shape:
- The desired artifact is not a live BLE stream. It is expected to be a stored, full-fidelity Dreem recording file, likely HDF5 `.h5`.
- Dreem is more like a store-and-forward Linux recorder than a simple live streamer.
- Public/academic references suggest dry electrodes around O1/O2/FpZ/F7/F8, 250 Hz-ish EEG, 24-bit frontend, and native sleep staging.

## Important Safety / Scope Note

Several offensive-style tests were attempted earlier in the project against my own device on my own LAN. SSH brute force, authentication guessing, and user enumeration are now explicitly stopped and should not be resumed.

## High-Level Conclusion

What seems ruled out:
- The normal app/BLE report path does not return raw `.h5`; it returns a tiny processed report payload.
- The backend `reportv2` path stores and returns the same compact report, not hidden raw data.
- Repointing upload/server URLs through the exposed BLE config path did not create a useful local upload target.
- The LAN service surface is essentially SSH only.
- Passive/public Dropbear research did not reveal a practical no-auth root path for the observed server.
- App APK/static analysis did not reveal embedded firmware images, raw data endpoints, or local raw HDF5 storage.
- Simple power/button timing does not enter SDP. A real physical TP10-to-GND short appears required.

What may still be viable:
- Physical i.MX6ULL SDP entry with a direct TP10-to-GND short during USB attach/power-up.
- If SDP entry is reliable, solve either HAB/secure boot, SPL/DRAM init, or use an accepted recovery path to expose/dump eMMC.
- More invasive eMCP/BGA storage work if someone has a known-good chip-off or in-circuit method.
- Discovering a valid old trust chain/backend upload route, if the device is refusing current cloud TLS.
- Recovering a real owner/current-app auth session, if one still exists somewhere, then checking whether any raw-data endpoints are owner-gated.

## Physical Hardware Attempts

### UART / Console

Tools used:
- Tigard V1.1 FT2232H.
- LA1010 logic analyzer.
- Multimeter.
- sigrok/PulseView.
- UART scan scripts across captured `.sr` files.

### Pad Map / Electrical Measurements

Photo/FCC review:
- Storage-side local photos show the i.MX6ULL above the Kingston eMCP on the `Femto MP-V2+` board.
- Storage-side visible labels include TP2, TP7, TP8, TP9, TP10, TP11, TP21, TP32, TP38, and TP39.
- FCC internal photo page 3 made the CPU/eMCP/USB-side labels TP2, TP7, TP9, TP10, TP11, TP32, and TP39 clearer.
- The acquisition/analog board also has labels such as TP2, TP3, TP5, TP6, TP7, TP8, TP9, TP10, TP12, and TP13, but those are not on the CPU/eMCP storage side.
- No photo showed an obvious grouped eMMC service footprint for CLK/CMD/DAT0/DAT1/DAT2/DAT3, and no confirmed reset/boot-mode/JTAG pad group has been identified.

Initial continuity-mode notes, before later ohms/voltage re-measurement:

| Pad | Continuity-mode observation |
| --- | --- |
| TP9 | No beep / no useful initial value reported |
| TP32 | Ground, `0` |
| TP11 | One beep for a millisecond, then beep stops; `.062` |
| TP38 | No useful initial value reported |
| TP39 | Ground, `0` |
| TP7 | No beep / no useful initial value reported |
| TP10 | Initially reported `0.8`, corrected to `.080` |
| TP2 | No beep / no useful initial value reported |
| TP8 | No beep / no useful initial value reported |
| TP3 | Ground-like initial reading, `.027` |
| Other listed pads | No beep; meter showed `OL` in continuity mode |

Later ohms-to-ground readings:

| Pad | Ohms-to-ground observation |
| --- | --- |
| TP9 | Starts around 300 kOhm and increases |
| TP32 | About `0.6` ohm |
| TP11 | Starts around 400 kOhm and increases |
| TP38 | Starts around 300 kOhm and increases |
| TP39 | About `0.5` ohm |
| TP7 | Starts around 300 kOhm and increases |
| TP10 | Starts around 400 kOhm and increases |
| TP2 | Jumps between about 60 kOhm and 250 kOhm |
| TP8 | Starts around 100 kOhm and increases |
| TP3 | Starts around 300 kOhm and increases |
| Two smaller unlabeled pads above TP8 | Start around 300 kOhm and increase |

Interpretation: TP32 and TP39 are the best ground candidates from the measured set. TP3 looked ground-like in the first continuity pass but did not look like a hard ground in later ohms readings.

USB-powered voltage readings:

| Pad | Voltage |
| --- | ---: |
| TP2 | `4.33 V` |
| TP7 | `4.28 V` |
| TP8 | `3.38 V` |
| TP9 | `3.28 V` |
| TP10 | `1.81 V` |
| TP11 | `0.003 V` |
| TP38 | `3.14 V` |
| TP3 | `3.11 V` |

Additional unlabeled readings:
- Two unlabeled pads near TP8: left around `3.1 V`, right `0 V`.
- Two unlabeled pads underneath/top near the vendor-date area: both around `3.1 V`.
- One unlabeled board-edge pad: no beep, around 300 kOhm and rising.
- One probed pad caused the LED to turn green during probing, unlike the others, but it was not conclusively identified.

What was tried:
- Looked for UART on exposed pads.
- Measured/debugged likely rail voltage. Later evidence points to 3.3 V, not 1.8 V.
- Early tests were weaker because common ground was missing in some captures.
- Later common-ground captures still did not produce readable boot logs.
- Searched logic analyzer captures for common boot strings and serial text.

Result:
- No credible U-Boot/Linux console found.
- UART data seen was either silence or noise/garbage, not readable boot output.
- Possible explanations: wrong pad, disabled console, missed timing, or console on another interface.

Pad/signal notes from the saved captures:

| Pad/net label from notes | Observation | Interpretation |
| --- | --- | --- |
| TP32, TP39 | Identified visually/electrically as likely grounds. | Used/considered as reference ground candidates. |
| Debug rail | Later work indicates 3.3 V logic is more likely than 1.8 V. | Use 3.3 V-safe tools/settings unless re-measured otherwise. |
| TP3 boot capture | 5 MS/s, 15 s window, all channels high, zero transitions. | No UART-looking activity. |
| TP11 boot capture | 5 MS/s, 15 s window; one channel had 1 to 18 transitions and about 80% high; others stayed high. | Not a readable UART console. |
| TP2 boot capture | 5 MS/s, 15 s window; one channel had 14,458 transitions but about 99.6% high; UART decoder found no valid candidates. | Activity exists, but not readable UART at tested baud/inversion settings. |
| TP8 boot capture | 5 MS/s, about 13.6 s usable; one transition, about 76.5% high. | Not a UART console. |
| TP9 boot capture | 5 MS/s, 15 s window; 3 transitions, about 85 to 87% high. | Not a UART console. |
| TP10 boot capture | 5 MS/s, 15 s window; 2 transitions, about 34% high. | Looks like a strap/control-ish line candidate, not a chatty UART line. |
| TP38 boot capture | 5 MS/s, 15 s window; one transition, about 76% high. | Not a UART console. |
| `current_uart_pin_level` capture | 2 MS/s, all channels high, zero transitions. | Suspected UART path idle-high, but no boot text/activity seen. |
| `vd1` capture | Activity present; inverted high-baud decoder produced noisy candidates around 1.5 to 2 Mbaud, no keywords/readable text. | Likely not console, or not decoded correctly. |
| `u8left` / `u8right` captures | Some activity, but decoder produced no valid UART candidates. | Possibly unrelated digital activity. |

Serial-capture notes:
- 115200 8N1 captures without a solid setup produced either zero bytes or very large runs of garbage bytes.
- Common-ground retries still did not produce readable boot output.
- A scan across 34 sigrok `.sr` captures found only noisy inverted high-baud candidates and no credible strings such as U-Boot, Linux, Freescale, i.MX, login prompts, etc.

### SDP / U-Boot / USB Mass Storage

What was learned:
- The SoC is NXP i.MX6ULL and should have ROM SDP mode.
- SDP USB ID to watch for is `15a2:0080`.
- Direct TP10-to-GND short reportedly worked historically to get ROM behavior; a 1 kOhm resistor was too gentle.
- Polling `/sys/bus/usb` for vendor/product is more reliable than watching `lsusb` manually.

Payload/tool work:
- Installed/prepared `uuu`, `imx_usb`, `openocd`, `h5ls`, `binwalk`, `flashrom`, `sigrok-cli`, CST/SRK tooling, etc.
- Built/prepared U-Boot UMS payloads based on i.MX6UL EVK assumptions:
  - 9x9 LPDDR2-flavored path looked more plausible.
  - 14x14 DDR3 path was also prepared as fallback.
- Added a physical SDP watcher/triage runner that watches for `15a2:0080`, runs safe SDP triage, tries U-Boot UMS scripts, watches for USB mass storage, dumps a new USB disk read-only, and carves HDF5 signatures if an image appears.

Observed behavior:
- Plain power/button timing repeatedly did not enumerate SDP.
- No USB mass storage device appeared.
- A previous U-Boot/SPL attempt did not re-enumerate or expose UMS; the device stayed in SDP and produced no UART output.
- HAB/production mode was observed, so unsigned SPL/U-Boot may be rejected.
- `imx_usb` readback in SDP reported `HAB security state: production mode (0x12343412)`.
- SDP was real at least briefly in earlier manual windows: USB showed `15a2:0080` / `SP Blank 6ULL` / `i.MX 6ULL SystemOnChip in RecoveryMode`.
- An OCRAM load test failed with `report 2 out err=-7`, so even a small raw load was not straightforward in that run.
- A UUU OCRAM test saw a fresh SDP device but failed due a local script/path issue before proving execution.
- `imx_usb_loader` mapped the device to `mx6ull_usb_work.conf`.
- One SPL attempt appeared to load from the tool's perspective: reported SPL size was 39,936 bytes, IVT header at `0x00907400`, entry point `0x00908000`, and jump to `0x00907400`.
- After that jump there was still no useful UART output, U-Boot prompt, re-enumeration, UMS gadget, or block device.

Useful register/fuse observations from SDP read attempts:
- IOMUX/USDHC state could be read over SDP while in ROM mode.
- Fuse scan confirmed production HAB state.
- Fuses included values consistent with the device MACs, but I am omitting those identifiers here.
- USDHC register snapshots showed both controller regions readable, suggesting ROM/debug reads were working at least at the register level.

Most likely explanations:
- The physical short timing was not actually achieved during the automated runs.
- HAB/secure boot blocks unsigned code.
- SPL starts but DRAM init fails.
- Console/USB path is wrong even if code starts.

Current best physical next step:
- Have a human directly short TP10 to GND during USB attach/power-up while a host watches for SDP/UMS.
- Do not repeat plain power/button timing without the TP10 short; that is already a dead end.

### JTAG / eMMC / Chip-Off

What was considered:
- Tigard JTAG/OpenOCD config was prepared.
- eMCP chip-off was considered.
- SPI flash dumping was considered, but no separate SPI NOR was proven to hold the desired data.
- In-circuit eMMC tap was considered but needs confirmed CLK, CMD, DAT0, power, ground, and a way to keep the i.MX6 host inactive/high-Z.

Result:
- No confirmed JTAG session.
- eMCP is BGA, so storage access is invasive and not clip-friendly.
- Chip-off or board-level eMMC access may still be a valid fallback for someone with the right tools.
- The Kingston eMCP is consistent with 4 GB eMMC plus 4 Gb LPDDR2, eMMC 5.0/HS200, 162-ball FBGA, about 11.5 x 13 x 1.0 mm.
- Photo review did not reveal a practical non-chip-off eMMC breakout. Without x-ray, board files, finer continuity tracing, or a known ballout-to-via map, wiring random pads to an SD/eMMC reader is too likely to hit power/USB/reset/control nets.

## BLE / App Protocol Attempts

### BLE GATT Inventory

Known/observed characteristic roles include:
- `D102`: Wi-Fi config write path.
- `D301`: live preview notifications.
- `D302`: recording start/stop-ish control.
- `D304`: record status.
- `D309`: record UUID/status.
- `D401`: latest record/report UUID.
- `D402`: latest report data.
- `D701`, `D705`, `D709`: firmware/hardware version reads.
- `D704`: firmware status notify.
- `D706`: firmware update trigger write.
- `D901`: user ID.
- `D902`: server URL config.
- `D904`: server password/status read.
- `D905`: server password write.

Pixel-side helper app was used for BLE reads/writes/notify because host BlueZ behavior was flaky.

Handle notes from previous GATT inventories:
- `D905` server password value was seen around handle `0x003d`.
- `D902` server URLs around `0x0043`.
- `D901` user ID around `0x0045`.
- `D402` latest report data around `0x0075`.
- `D401` latest report UUID around `0x0077`.
- `D309` record UUID/status around `0x0085`.
- `D301` live preview notify around `0x0095`, with CCCD around `0x0096`.

### Recording / Report Path

What was tried:
- Started/stopped a fresh nap-style recording via BLE.
- Read latest record/report UUID.
- Pulled the latest report via BLE.
- Tried Classic/RFCOMM report fetch paths as well.
- Reviewed the Android APK’s report download/storage/upload code.

Result:
- The official report path is BLE `D401`/`D402`, matching Classic IDs `601`/`602`.
- The retrieved file was about 402 bytes.
- It was a ZIP containing `reporting_v2.data`.
- It did not contain HDF5 magic and was not a raw `.h5`.
- The app stores/uploads those exact compact report bytes; it does not transform them into HDF5.

Conclusion:
- `D402` / Classic `602` is a compact processed report path, not the raw overnight recording.
- Repeating report pulls is unlikely to help unless a new characteristic/protocol path is found.

### Live Preview

What was tried:
- Subscribed to `D301`.
- Captured roughly 20 seconds of notifications.

Result:
- Data looked like low-rate preview/display samples, likely four little-endian floats per frame.
- Useful as a connectivity smoke test, but not the stored overnight `.h5`.

### Unknown BLE Characteristics

What was tried:
- Passive reads of `D007` and `D008`.

Result:
- Both appeared READ|WRITE, but passive reads returned status 2 / zero-length data.
- Random writes were intentionally avoided.

Conclusion:
- Do not blindly fuzz/write unknown BLE characteristics without a stronger hypothesis.

### Firmware-Related BLE

What was tried:
- Read firmware/hardware version characteristics.
- Subscribed to firmware status notify.
- Reviewed app firmware update code.

Result:
- Real/root firmware versions read as `4.7.11`.
- Hardware version read as `v2plus_medical`.
- Passive `D704` firmware notify did not emit useful data.
- App firmware update path appears to trigger headset-driven update via `D706`; no firmware bytes or download URLs were embedded in the app.

Conclusion:
- No passive firmware/rootfs extraction path found.
- A `D706` firmware trigger loop was avoided because it is state-changing and could brick or waste time without firmware bytes.

## Wi-Fi / Server Config / Upload Attempts

### BLE Wi-Fi And Server Configuration

What was learned:
- `D102` writes encrypted/framed Wi-Fi JSON.
- Wi-Fi provisioning worked best with USB power disconnected / non-charging state.
- USB-power-connected Wi-Fi writes could show BLE success while the internal Wi-Fi status remained wrong.
- `D901` accepts UUID-shaped user IDs.
- `D902` is server URL config with JSON length prefix.
- `D905` is server password write; `D904` reflects encrypted/status state.
- `D902` JSON shape is length-prefixed and contains `user_api_url` / `user_auth_url`.
- Production Rythm URL config writes returned success; local and arbitrary URL attempts generally returned status 3.
- `D904` clearing to four zero bytes was treated as the good server-password/status state after `D905`.

What was tried:
- Restored production server URLs/password.
- Tried local HTTP/HTTPS server URLs.
- Tried local high-port and port 81 capture ideas.
- Tried public-looking and parser-bypass URL shapes.

Result:
- Production Rythm URLs were accepted.
- Local or arbitrary URLs were rejected with status 3 or otherwise did not take.
- D905 password write could be accepted, but did not cause a raw upload by itself.

Conclusion:
- Server password/config state can be manipulated to some degree, but not enough to redirect raw upload to a local listener so far.

### Network Upload Captures

What was tried:
- AP-side captures through the UniFi network.
- host captures.
- USB-power/charging state changes, button wake/hold attempts, and app foreground triggers.
- Checked DNS/SNI/TLS conversation sizes.

Results:
- The headset associated on the LAN when online.
- Captures after upload triggers showed DNS for `www.rythm.co` / `api.rythm.co` and small TLS conversations.
- Conversation sizes were tiny, around a few KB, far too small for raw H5/EDF.
- Some windows showed only DHCP/ARP.
- No large raw-data upload was observed.

Conclusion:
- The device did not upload a raw file during these tested windows.
- If raw upload exists, it may be blocked by trust/auth/state, or only occur under conditions not reproduced.

### TLS / Trust Store Hypothesis

What was observed:
- A real TLS tunnel saw SNI `login.rythm.co`.
- Server chain involved Let’s Encrypt/ISRG roots.
- The headset sent ClientHello but did not proceed to useful API upload traffic in that test.

Hypothesis:
- The old device trust store may reject the current production certificate chain, or some old auth path is no longer compatible.

What did not work:
- Local self-signed/production-host MITM approaches failed at trust/cert validation.
- Routing production HTTPS through a local box caused route-loop or trust issues.

## Backend / API Attempts

What was tried:
- Created/used disposable backend accounts.
- Resolved the headband by address through backend routes.
- Queried configuration, content, firmware, headband, report, dataupload-like endpoints.
- Used backend `update_password` route after allotment/association.
- Checked `reportv2` behavior.
- Checked `dataupload` status/detail guesses.
- Uploaded the compact BLE report manually to `reportv2` to see if backend transformed it.

Important findings:
- Headband resolution accepted Wi-Fi MAC underscore form, not colon/lowercase/BLE variants.
- Configuration exposed firmware/content IDs/storage counters/nickname, but no raw reports, rootfs, SSH credentials, or server password.
- `update_password` could return a server-password value after proper association, and D905 could write it to the headset.
- That password did not work for SSH users tested earlier.
- `reportv2` stores and returns the compact `reporting_v2.data` ZIP exactly. It does not expose a hidden raw `.h5`.
- `dataupload` checks returned 401/403/404/empty JSON-style responses, not raw files.
- Backend content metadata largely referenced media/UI content, not firmware/rootfs.
- Content objects were mostly ZIP/audio/image packages, not bootloader/rootfs/firmware payloads.
- Direct object fetches without signed URLs returned HTTP 403.
- API route sweeps found many resources but no raw-file route reachable with the available account state.

Conclusion:
- Backend-visible report APIs do not appear to contain the raw `.h5` for this device/account state.
- A real owner account/session could still be worth checking if available, but disposable/current test accounts did not expose raw data.

## Android App / APK / Pixel Attempts

What was used:
- Rooted Pixel 7.
- Patched/debuggable Dreem app.
- Production Dreem app tested separately.
- APK decompilation/static analysis.
- App DB/Hawk/conceal preference inspection.

What was tried:
- Pulled app sandbox data.
- Inspected SQLite databases.
- Decrypted accessible Hawk/conceal keys.
- Looked for `.h5`, `hdf5`, report artifacts, auth tokens, bearer/JWT tokens, and raw data paths.
- Reviewed code around BLE reports, firmware updates, content downloads, server config, and upload.

Results:
- Current/patched app state had Dreemer/HeadbandConfig rows but NightReport/NightScore/etc. were empty.
- No local HDF5 files were found.
- Current auth/JWT tokens were absent in the inspected state.
- Refresh token marker was boolean-like, not a usable token string.
- Production app owner state also did not expose useful current auth or raw local files.
- Google auth path failed due package/signature/API-console mismatch or backend rejection.
- App firmware/content paths did not contain firmware bytes or raw extraction endpoints.

Conclusion:
- The phone/app path did not contain the raw file or a usable owner auth token.
- The official app report flow confirms the compact report behavior rather than raw export.

## LAN / SSH Surface

What was observed:
- When online, the headset exposes SSH on TCP/22.
- Full/common TCP scans repeatedly showed no other useful open ports.
- UDP scans did not expose useful services.
- SSH banner observed as Dropbear `2016.74` earlier and `2018.76` later/current.

What was tried earlier:
- Passive banner/KEX checks.
- Public vulnerability research.
- Some earlier SSH credential guessing/user-enum style work happened, but was explicitly stopped later.

Results:
- No practical no-auth Dropbear root exploit was identified for the observed version.
- User-enum/timing/malformed-key approaches did not produce a useful signal.
- Saved/backend-derived secret candidates did not produce root access.

Current rule:
- Do not resume SSH brute force, password guessing, or user enumeration.
- The SSH surface has not yielded a path and is not the recommended next direction.

## Public / Community / External References Checked

References considered:
- FCC/internal photos for the Dreem 2.
- MajorInput Dreem teardown article.
- DreemEEG / old BLE live-stream prior art.
- Dreem-Organization GitHub repos.
- Dreamento / Wearipedia style downstream tooling.
- Alfin app public references.
- Dreem support docs and archived pages.

Conclusion:
- Public repos/tools are useful once raw data exists, or for low-rate/live BLE experiments.
- I did not find a public software path that extracts stored raw `.h5` from this Dreem 2.
- One community note suggested raw EEG may only be available on Dreem 2 Medical, and this device reports `v2plus_medical`, but the raw file is still not exposed through the app/report path.

## Things I Would Not Repeat

These paths are likely spent unless someone brings new evidence:

- Pulling BLE `D402` / Classic `602` expecting raw `.h5`.
- Re-fetching the same `reportv2` signed download.
- D905-only password write followed by the same upload/report checks.
- Plain power/button SDP attempts without physically shorting TP10 to GND.
- D007/D008 passive reads.
- Blind BLE fuzzing/writes to unknown characteristics.
- D706 firmware trigger loops without firmware bytes and a recovery plan.
- App firmware URL greps/direct S3 fetches without a newly discovered signed URL.
- Local D902 rewrite attempts unless someone can show the exact accepted server URL format or trust-store bypass.
- SSH brute force/auth guessing/user enumeration.

## Open Questions For The Forum

I would especially appreciate input on:

1. Has anyone reliably entered i.MX6ULL SDP on Dreem 2, and can they confirm the TP10-to-GND timing?
2. Has anyone run signed or accepted code through Dreem 2 SDP, or confirmed HAB/secure boot behavior?
3. Does anyone have a known-good U-Boot/SPL config for this exact eMCP/LPDDR2 package?
4. Has anyone identified JTAG pads or achieved an OpenOCD session on the Femto MP-V2 board?
5. Has anyone dumped the eMCP/eMMC from a Dreem 2 and found where raw recordings live?
6. Does anyone know whether `reporting_v2.data` can reference a raw object elsewhere, or is it purely the processed report?
7. Are there additional BLE characteristics beyond the `Dxxx` report/status/config surface that expose raw chunks?
8. Is there a known legacy TLS/root-CA issue with Dreem production servers that prevents upload, and can it be worked around without device root?
9. Does an authenticated original owner account expose any raw-data endpoint not visible from disposable/current test accounts?
10. Has anyone seen firmware update packages for `4.7.11+PRODUCTION` or Dreem 2 Medical that could be analyzed for boot/update behavior?

## Current Practical Next Step

If I resume hands-on work, I would focus on the physical path:

- Aim the webcam at the board/LED area.
- Start the SDP/UMS watcher.
- Have a human apply a direct TP10-to-GND short before and during USB attach / power-up.
- Watch for `15a2:0080`.
- If SDP appears, attempt minimal triage and UMS/eMMC exposure.
- If a block device appears, dump it read-only and carve for HDF5 magic.

Everything else I tried so far has led back to compact processed reports, not raw `.h5`.
