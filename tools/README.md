# Maintained tools

These are the reusable utilities that remain useful for a future recovery attempt.

## SDP, UMS, and HDF5

- `dreem_physical_sdp_window.py` coordinates a human-assisted TP10-to-GND SDP window, optional triage, optional U-Boot UMS boot, and UMS watch.
- `dreem_sdp_recovery_watch.py` watches for the i.MX6ULL SDP USB ID.
- `dreem_sdp_triage.py` runs non-persistent SDP triage using `recovery/imx-usb/` configs.
- `dreem_sdp_checkdata.py` builds and runs SDP check-data probes.
- `dreem_ums_dump_watch.py` watches for a new USB mass-storage disk and can image it read-only.
- `dreem_h5_carve.py` scans dumps for HDF5 magic and validates candidates with `h5ls`.

## Bluetooth

- `dreem_att_client.c` is a minimal raw ATT client experiment for known-handle access.
- `dreem_btclassic_report_fetch.py` probes Bluetooth Classic report IDs.
- `dreem_btclassic_request.py` sends a single Bluetooth Classic request.
- `dreem_btclassic_wifi_auth.py` builds and sends the Bluetooth Classic Wi-Fi auth payload.

The Bluetooth Classic helpers require an explicit `--address`; pass the address for the headset you are authorized to test. Supply Wi-Fi credentials through runtime arguments or ignored configuration files.

## Native helper

`native/dreem_att_read/` contains the C source for the ATT read helper.

## Optional bench integrations

The physical SDP runner can coordinate an operator-supplied charger helper and Fingerbot API. Provide your own implementations with `--charger-helper`, `--fingerbot-base-url`, and `--fingerbot-token-json`. The default ignored locations are `private/ha_plug.sh` and `private/fingerbot_login.raw.json`.
