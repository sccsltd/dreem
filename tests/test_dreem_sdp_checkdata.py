import pathlib
import json
import tempfile
import unittest


try:
    from tools import dreem_sdp_checkdata
except ImportError:
    dreem_sdp_checkdata = None


class CheckDataDcdTests(unittest.TestCase):
    def setUp(self):
        if dreem_sdp_checkdata is None:
            self.fail("tools.dreem_sdp_checkdata module is missing")

    def test_builds_single_checkdata_dcd_with_count(self):
        blob = dreem_sdp_checkdata.build_dcd_checkdata(
            address=0x80000000,
            mask=0x00000020,
            count=0x00001000,
            width=4,
            flags=0x10,
        )

        self.assertEqual(
            blob.hex(),
            "d2001440"
            "cf001014"
            "80000000"
            "00000020"
            "00001000",
        )

    def test_rejects_misaligned_32_bit_address(self):
        with self.assertRaisesRegex(ValueError, "aligned"):
            dreem_sdp_checkdata.build_dcd_checkdata(
                address=0x80000002,
                mask=1,
                count=1,
                width=4,
                flags=0x10,
            )

    def test_writes_uuu_script_pointing_to_generated_dcd(self):
        with tempfile.TemporaryDirectory() as td:
            out_dir = pathlib.Path(td)
            dcd_path = out_dir / "probe.dcd"
            uuu_path = out_dir / "probe.uuu"

            dreem_sdp_checkdata.write_probe_files(
                dcd_path=dcd_path,
                uuu_path=uuu_path,
                address=0x0091F000,
                mask=0x1,
                count=7,
                width=4,
                flags=0x08,
            )

            self.assertTrue(dcd_path.read_bytes().startswith(bytes.fromhex("d2001440cf00100c")))
            self.assertEqual(
                uuu_path.read_text(encoding="utf-8"),
                "uuu_version 1.4.72\nSDP: dcd -f probe.dcd\n",
            )

    def test_cli_dry_run_writes_probe_summary(self):
        with tempfile.TemporaryDirectory() as td:
            rc = dreem_sdp_checkdata.main(
                [
                    "--address",
                    "0x80000000",
                    "--mask",
                    "0x20",
                    "--count",
                    "4096",
                    "--condition",
                    "all-set",
                    "--out-dir",
                    td,
                    "--dry-run",
                ]
            )

            out_dir = pathlib.Path(td)
            self.assertEqual(rc, 0)
            self.assertEqual((out_dir / "probe.dcd").read_bytes().hex()[8:16], "cf001014")
            summary = (out_dir / "summary.json").read_text(encoding="utf-8")
            self.assertIn('"condition": "all-set"', summary)
            self.assertIn('"ran_uuu": false', summary)

    def test_cli_no_device_summary_includes_finish_time(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as sysfs:
            rc = dreem_sdp_checkdata.main(
                [
                    "--address",
                    "0x80000000",
                    "--mask",
                    "0x20",
                    "--count",
                    "4096",
                    "--out-dir",
                    td,
                    "--sysfs-root",
                    sysfs,
                ]
            )

            summary = json.loads((pathlib.Path(td) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 2)
            self.assertEqual(summary["error"], "SDP device not present")
            self.assertEqual(summary["devices"], [])
            self.assertIn("finished_utc", summary)

    def test_wait_for_sdp_devices_returns_existing_match(self):
        self.assertTrue(
            hasattr(dreem_sdp_checkdata, "wait_for_sdp_devices"),
            "wait_for_sdp_devices is missing",
        )
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            dev = root / "3-2"
            dev.mkdir()
            (dev / "idVendor").write_text("15a2\n", encoding="utf-8")
            (dev / "idProduct").write_text("0080\n", encoding="utf-8")
            (dev / "busnum").write_text("003\n", encoding="utf-8")
            (dev / "devnum").write_text("042\n", encoding="utf-8")

            devices = dreem_sdp_checkdata.wait_for_sdp_devices(
                sysfs_root=root,
                timeout=0,
                poll_interval=0.01,
            )

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["busnum"], "003")

    def test_builds_bit_campaign_masks(self):
        self.assertTrue(
            hasattr(dreem_sdp_checkdata, "build_bit_campaign"),
            "build_bit_campaign is missing",
        )

        probes = dreem_sdp_checkdata.build_bit_campaign(
            address=0x80000000,
            count=4096,
            condition="all-set",
            first_bit=4,
            bit_count=3,
        )

        self.assertEqual([probe["bit"] for probe in probes], [4, 5, 6])
        self.assertEqual([probe["mask"] for probe in probes], [0x10, 0x20, 0x40])
        self.assertEqual([probe["stem"] for probe in probes], ["bit04", "bit05", "bit06"])

    def test_cli_bit_campaign_dry_run_writes_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            try:
                rc = dreem_sdp_checkdata.main(
                    [
                        "--address",
                        "0x80000000",
                        "--count",
                        "4096",
                        "--condition",
                        "all-set",
                        "--bit-campaign",
                        "--first-bit",
                        "0",
                        "--bit-count",
                        "3",
                        "--out-dir",
                        td,
                        "--dry-run",
                    ]
                )
            except SystemExit as exc:
                self.fail(f"bit-campaign CLI is missing or invalid: exited {exc.code}")

            out_dir = pathlib.Path(td)
            manifest = json.loads((out_dir / "campaign_manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))

            self.assertEqual(rc, 0)
            self.assertEqual(summary["mode"], "bit-campaign")
            self.assertEqual(len(manifest["probes"]), 3)
            self.assertEqual(manifest["probes"][2]["mask"], "0x00000004")
            self.assertTrue((out_dir / "bit02.dcd").exists())
            self.assertEqual(
                (out_dir / "bit02.uuu").read_text(encoding="utf-8"),
                "uuu_version 1.4.72\nSDP: dcd -f bit02.dcd\n",
            )


if __name__ == "__main__":
    unittest.main()
