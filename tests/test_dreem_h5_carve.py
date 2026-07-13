import json
from pathlib import Path
import tempfile
import unittest


try:
    from tools import dreem_h5_carve
except ImportError:
    dreem_h5_carve = None


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT
    / "artifacts"
    / "src"
    / "dreem_org_extra"
    / "dosed"
    / "tests"
    / "test_files"
    / "h5"
    / "23c61485-a9a5-478b-8115-f34b883876b8.h5"
)
HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


class DreemH5CarveTests(unittest.TestCase):
    def setUp(self):
        if dreem_h5_carve is None:
            self.fail("tools.dreem_h5_carve module is missing")

    def test_find_magic_offsets_scans_binary_file(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "image.bin"
            image.write_bytes(b"pad" + HDF5_MAGIC + b"middle" + HDF5_MAGIC + b"tail")

            self.assertEqual(dreem_h5_carve.find_magic_offsets(image), [3, 17])

    @unittest.skipUnless(FIXTURE.is_file(), "upstream HDF5 fixture is not included")
    def test_carves_embedded_fixture_and_validates_with_h5ls(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            image = td_path / "emmc.bin"
            offset = 4096
            image.write_bytes(b"\0" * offset + FIXTURE.read_bytes() + b"trailer")

            results = dreem_h5_carve.carve_image(
                image=image,
                out_dir=td_path / "carved",
                max_bytes=FIXTURE.stat().st_size + 128,
                validate=True,
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["offset"], offset)
            self.assertTrue(results[0]["h5ls_ok"])
            carved = Path(results[0]["path"])
            self.assertEqual(carved.read_bytes()[:8], HDF5_MAGIC)

    @unittest.skipUnless(FIXTURE.is_file(), "upstream HDF5 fixture is not included")
    def test_cli_writes_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            image = td_path / "emmc.bin"
            image.write_bytes(b"prefix" + FIXTURE.read_bytes())
            out_dir = td_path / "out"

            rc = dreem_h5_carve.main(
                [
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--max-bytes",
                    str(FIXTURE.stat().st_size + 64),
                ]
            )

            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(rc, 0)
            self.assertEqual(manifest["candidate_count"], 1)
            self.assertEqual(manifest["validated_count"], 1)
            self.assertEqual(manifest["candidates"][0]["offset_hex"], "0x0000000000000006")


if __name__ == "__main__":
    unittest.main()
