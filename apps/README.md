# Helper applications

`android/` contains independent helper projects rather than one shared Android build:

- `dreem-ble-helper/` — BLE/GATT research app for pairing, provisioning, recording control, report retrieval, and characteristic probes.
- `dreem-auth-cli/` — shell-launched Google/Rythm authentication probe.
- `dreem-auth-instrumentation/` — instrumentation package for authentication checks in the target-package context.
- `dreem-google-auth-probe/` — standalone Activity that requests Google tokens and tests the legacy Rythm exchange.
- `root-bluetooth-pairing-cli/` — root-context CLI for hidden-API Bluetooth LE pairing confirmation.

`magisk-modules/` contains the privileged-system-app overlay for the BLE helper.
