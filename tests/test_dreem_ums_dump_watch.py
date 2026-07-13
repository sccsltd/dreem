import json
from pathlib import Path
import tempfile
import unittest


try:
    from tools import dreem_ums_dump_watch
except ImportError:
    dreem_ums_dump_watch = None


HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


class DreemUmsDumpWatchTests(unittest.TestCase):
    def setUp(self):
        if dreem_ums_dump_watch is None:
            self.fail("tools.dreem_ums_dump_watch module is missing")

    def test_flattens_lsblk_tree_and_selects_new_positive_size_usb_disk(self):
        data = {
            "blockdevices": [
                {"name": "sda", "path": "/dev/sda", "type": "disk", "tran": "usb", "size": 0},
                {
                    "name": "sdb",
                    "path": "/dev/sdb",
                    "type": "disk",
                    "tran": "usb",
                    "size": 4096,
                    "children": [{"name": "sdb1", "path": "/dev/sdb1", "type": "part", "size": 2048}],
                },
                {"name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk", "tran": "nvme", "size": 1024},
            ]
        }

        devices = dreem_ums_dump_watch.flatten_lsblk(data)
        candidates = dreem_ums_dump_watch.select_new_usb_disks(devices, baseline_paths={"/dev/sda"})

        self.assertIn("/dev/sdb1", {device["path"] for device in devices})
        self.assertEqual([candidate["path"] for candidate in candidates], ["/dev/sdb"])

    def test_selects_replaced_baseline_path_when_usb_identity_changes(self):
        baseline = {
            "/dev/sda": {
                "path": "/dev/sda",
                "type": "disk",
                "tran": "usb",
                "size": 0,
                "model": "Logitech StreamCam",
                "serial": "old",
            }
        }
        devices = [
            {
                "path": "/dev/sda",
                "type": "disk",
                "tran": "usb",
                "size": 64 * 1024 * 1024,
                "model": "U-Boot UMS disk",
                "serial": "dreem",
            }
        ]

        candidates = dreem_ums_dump_watch.select_new_usb_disks(
            devices,
            baseline_paths=set(baseline),
            baseline_devices_by_path=baseline,
        )

        self.assertEqual([candidate["path"] for candidate in candidates], ["/dev/sda"])

    def test_watch_once_without_new_disk_writes_summary(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            lister = lambda: [{"path": "/dev/sda", "type": "disk", "tran": "usb", "size": 0}]

            rc = dreem_ums_dump_watch.watch(
                out_dir=td_path / "out",
                duration=0,
                poll_interval=0.01,
                once=True,
                dump=False,
                lister=lister,
            )

            summary = json.loads((td_path / "out" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 2)
            self.assertFalse(summary["disk_detected"])
            self.assertEqual(summary["candidates"], [])

    def test_watch_detects_new_usb_disk_and_can_copy_limited_image(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fake_disk = td_path / "fake-usb-disk.bin"
            fake_disk.write_bytes(b"prefix" + HDF5_MAGIC + b"\0" * 4096)
            calls = {"count": 0}

            def lister():
                calls["count"] += 1
                if calls["count"] == 1:
                    return []
                return [
                    {
                        "path": str(fake_disk),
                        "type": "disk",
                        "tran": "usb",
                        "size": fake_disk.stat().st_size,
                    }
                ]

            rc = dreem_ums_dump_watch.watch(
                out_dir=td_path / "out",
                duration=1,
                poll_interval=0.01,
                once=False,
                dump=True,
                max_bytes=32,
                carve=False,
                lister=lister,
            )

            summary = json.loads((td_path / "out" / "summary.json").read_text(encoding="utf-8"))
            image = Path(summary["dump"]["path"])
            self.assertEqual(rc, 0)
            self.assertTrue(summary["disk_detected"])
            self.assertEqual(image.read_bytes(), fake_disk.read_bytes()[:32])


if __name__ == "__main__":
    unittest.main()
