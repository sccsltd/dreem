# Hardware recovery assets

- `imx-usb/` — i.MX6ULL register, fuse, state, and OCRAM test configs
- `ocram/marker-write-smoke-test/` — minimal image that writes a marker into OCRAM
- `ocram/uuu-probes/` — UUU OCRAM and SoC-register read/write probes
- `openocd/` — JTAG/OpenOCD configuration
- `u-boot/ums-boot-assets/` — UUU launch scripts and matching UMS boot images
- `u-boot/build-configs/` — retained generated U-Boot configurations
- `uuu/ocotp-register-read-probe/` — standalone OCOTP register-read experiment

These payloads can affect attached hardware. Inspect each script and config before use.

The compiled U-Boot images and generated U-Boot configurations retain GPL-2.0-or-later provenance; see the [third-party notices](../THIRD_PARTY_NOTICES.md#u-boot-derived-recovery-files).
