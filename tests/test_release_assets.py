import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.release_assets import ASSETS, build_version, prepare


class ReleaseTests(unittest.TestCase):
    def test_version_validation(self):
        sha = "a"*40
        self.assertEqual(build_version("tag", "v1.2.3", sha), "v1.2.3")
        self.assertEqual(build_version("tag", "v1.2.3-rc.1", sha), "v1.2.3-rc.1")
        self.assertEqual(build_version("branch", "main", sha), "snapshot-"+sha[:12])
        for value in ("v../tag", "v1.2", "v1.0.0;echo test", "v01.0.0", "v1.0.0\n"):
            with self.assertRaises(ValueError): build_version("tag", value, sha)

    def test_requires_every_platform_asset(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                prepare(root, Path(root)/"out", "tag", "v1.0.0", "a"*40, "https://example.test/run")
            self.assertFalse((Path(root)/"out").exists())

    def test_prepares_versioned_assets_and_checksums(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for name in ASSETS:
                path = root/name
                if path.suffix == ".zip":
                    with zipfile.ZipFile(path, "w") as archive:
                        archive.writestr("test", "data")
                else:
                    path.write_bytes(b"unit-test-dmg-placeholder")
            output = root/"out"
            prepare(root, output, "tag", "v1.0.0", "a"*40, "https://example.test/run")
            self.assertEqual(len(list(output.iterdir())), 5)
            self.assertEqual(json.loads((output/"build-info.json").read_text())["commit"], "a"*40)
            for line in (output/"SHA256SUMS.txt").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(), digest)
            with self.assertRaises(FileExistsError):
                prepare(root, output, "tag", "v1.0.0", "a"*40, "https://example.test/run")
