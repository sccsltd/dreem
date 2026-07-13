import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "dreem_sdp_triage.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dreem_sdp_triage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DreemSdpTriageTests(unittest.TestCase):
    def test_find_sdp_devices_reads_matching_sysfs_entries(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dev = root / "3-2"
            dev.mkdir()
            (dev / "idVendor").write_text("15a2\n")
            (dev / "idProduct").write_text("0080\n")
            (dev / "busnum").write_text("003\n")
            (dev / "devnum").write_text("042\n")
            (dev / "product").write_text("i.MX 6ULL SystemOnChip in RecoveryMode\n")

            other = root / "3-3"
            other.mkdir()
            (other / "idVendor").write_text("18d1\n")
            (other / "idProduct").write_text("4ee7\n")

            devices = module.find_sdp_devices(root)

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["busnum"], "003")
        self.assertEqual(devices[0]["devnum"], "042")
        self.assertIn("i.MX 6ULL", devices[0]["product"])

    def test_no_wait_without_sdp_device_writes_summary_and_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            sysfs = temp / "sys"
            sysfs.mkdir()
            out = temp / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--no-wait",
                    "--sysfs-root",
                    str(sysfs),
                    "--out-dir",
                    str(out),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

            summary = json.loads((out / "summary.json").read_text())

        self.assertEqual(proc.returncode, 2)
        self.assertEqual(summary["error"], "SDP device not present")
        self.assertEqual(summary["devices"], [])
        self.assertIn("finished_utc", summary)


if __name__ == "__main__":
    unittest.main()
