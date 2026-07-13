# Evidence Summary

This file condenses the investigation into tested conclusions, reusable assets, and replay guidance. It is the fastest way to understand what worked, what did not, and which experiments are worth continuing.

## Physical SDP / UMS

Conclusion: the remaining credible path is physical i.MX6ULL Serial Downloader Protocol entry with a direct TP10-to-GND short during USB attach or power-up. Charger/fingerbot-only attempts did not enumerate SDP.

Reusable assets kept in this repo:

- `recovery/imx-usb/imx-register-probe.d/`
- `recovery/imx-usb/imx-fuse-scan.d/`
- `recovery/imx-usb/imx-usdhc-state.d/`
- `recovery/ocram/uuu-probes/`
- `recovery/u-boot/ums-boot-assets/`
- `tools/dreem_physical_sdp_window.py`
- `tools/dreem_sdp_triage.py`
- `tools/dreem_ums_dump_watch.py`
- `tools/dreem_h5_carve.py`

Do not repeat: power/button/charger/fingerbot SDP windows without the physical TP10-to-GND condition.

## U-Boot Build

Conclusion: two experimental i.MX6UL U-Boot UMS payload families were prepared. The 9x9/LPDDR2-flavored path is considered more plausible than the 14x14/DDR3 fallback, but neither yielded UMS in the previous windows.

Reusable assets kept in this repo:

- `recovery/u-boot/build-configs/u-boot-mx6ul-9x9-ums/`
- `recovery/u-boot/build-configs/u-boot-mx6ul-14x14-ums/`
- `recovery/u-boot/ums-boot-assets/boot_mx6ul_9x9_autoums.uuu`
- `recovery/u-boot/ums-boot-assets/boot_mx6ul_14x14_autoums.uuu`

Risk: HAB/secure boot, DRAM init mismatch, or missing console/USB path may block these unsigned payloads.

## BLE Report Path

Conclusion: the app-visible report path is compact processed data, not raw HDF5. BLE `D401`/`D402` and Bluetooth Classic IDs `601`/`602` point to the same report surface. The retrieved payload was a small ZIP containing `reporting_v2.data`.

Reusable assets kept in this repo:

- `tools/dreem_btclassic_report_fetch.py`
- `tools/dreem_btclassic_request.py`
- `tools/dreem_btclassic_wifi_auth.py`
- `tools/dreem_att_client.c`

Do not repeat: pulling `D402` or Classic `602` expecting raw `.h5` without new protocol evidence.

## Backend / Report / Dataupload

Conclusion: backend `reportv2` returns the same compact report bytes and does not expose a hidden raw `.h5` in the tested account state. Dataupload/status guesses did not reveal raw objects. D905 password writes can clear server-password state, but did not trigger raw upload or SSH access.

Do not repeat: D905-only password writes followed by the same AP capture, `reportv2`, and `dataupload` checks.

## Pixel / App Data

Conclusion: rooted Pixel app pulls and Hawk/Conceal inspection did not produce a raw HDF5 file or usable current Rythm auth/JWT bearer. The current app state was useful for protocol understanding but not for extraction.

Reproduce app-data analysis only against an account and device you are authorized to inspect. Keep shared preferences, Hawk XML, databases, device backups, and token material out of version control.

## Firmware / Content Audit

Conclusion: app/APK and backend content metadata did not expose firmware/rootfs images. Observed content objects were audio/UI/media packages or metadata, not raw EEG acquisition paths. Direct object fetches without signed URLs returned access denied.

Do not repeat: direct S3 fetches or app firmware URL greps without a new signed URL, firmware package, or endpoint clue.

## Passive SSH Surface

Conclusion: the headset exposes SSH on TCP/22 when online. The observed Dropbear version did not yield a practical no-auth root path through passive review. Authentication guessing and broad user enumeration are stopped paths.

Current rule: do not run SSH brute force, password guessing, broad user enumeration, Hydra, Medusa, Ncrack, Patator, `sshpass`, `dropbear_user_enum.py`, or equivalent.
