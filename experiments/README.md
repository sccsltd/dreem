# Experiments

One-off research probes live here. These scripts are less stable than the utilities in `tools/` and should only be run against authorized devices and systems.

- `backend/` contains the mock request-capture backend, firmware proxy-traffic capture, record-ID probes, and device-session provisioning experiments.
- `security/decrypt_hawk_conceal_preferences.py` decrypts locally supplied Hawk/Conceal preference material into restricted outputs.
- `security/dreem-ssh-password-campaign/` contains the bounded SSH password-recovery experiment and its connectivity watchdog.
- `security/dropbear_user_enum.py` and `security/run_live_hydra_ipv6.py` document stopped historical approaches and must not be run without explicit authorization.
