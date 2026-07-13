import json
from pathlib import Path
import tempfile
import unittest


try:
    from tools import dreem_sdp_recovery_watch
except ImportError:
    dreem_sdp_recovery_watch = None


class DreemRecoveryWatchTests(unittest.TestCase):
    def setUp(self):
        if dreem_sdp_recovery_watch is None:
            self.fail("tools.dreem_sdp_recovery_watch module is missing")

    def test_find_sdp_devices_reads_sysfs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dev = root / "3-2"
            dev.mkdir()
            (dev / "idVendor").write_text("15a2\n", encoding="utf-8")
            (dev / "idProduct").write_text("0080\n", encoding="utf-8")
            (dev / "busnum").write_text("003\n", encoding="utf-8")
            (dev / "devnum").write_text("007\n", encoding="utf-8")
            (dev / "product").write_text("i.MX 6ULL Recovery\n", encoding="utf-8")

            devices = dreem_sdp_recovery_watch.find_sdp_devices(root)

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["devnum"], "007")
            self.assertIn("Recovery", devices[0]["product"])

    def test_watch_once_without_sdp_writes_summary(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            rc = dreem_sdp_recovery_watch.main(
                [
                    "--sysfs-root",
                    str(td_path / "sys"),
                    "--out-dir",
                    str(td_path / "out"),
                    "--duration",
                    "0",
                    "--once",
                    "--no-triage",
                ]
            )

            summary = json.loads((td_path / "out" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 2)
            self.assertFalse(summary["sdp_detected"])
            self.assertEqual(summary["events"][0]["devices"], [])
            self.assertIn("finished_utc", summary)

    def test_watch_once_with_sdp_runs_triage_command_when_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            sysfs = td_path / "sys"
            dev = sysfs / "3-2"
            dev.mkdir(parents=True)
            (dev / "idVendor").write_text("15a2\n", encoding="utf-8")
            (dev / "idProduct").write_text("0080\n", encoding="utf-8")

            commands = []

            def fake_run(cmd, cwd, out, timeout):
                commands.append(cmd)
                out.write_text("triage ok\n", encoding="utf-8")
                return {"cmd": cmd, "returncode": 0, "out": str(out)}

            rc = dreem_sdp_recovery_watch.watch(
                sysfs_root=sysfs,
                out_dir=td_path / "out",
                duration=0,
                poll_interval=0.01,
                once=True,
                run_triage=True,
                runner=fake_run,
            )

            summary = json.loads((td_path / "out" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertTrue(summary["sdp_detected"])
            self.assertEqual(len(commands), 1)
            self.assertIn("dreem_sdp_triage.py", " ".join(commands[0]))
            self.assertEqual(summary["triage"]["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
