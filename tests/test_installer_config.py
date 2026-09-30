import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build


class InstallerConfigTests(unittest.TestCase):
    def test_version_matches_release_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"VERSION").write_text("1.0.1\n", encoding="utf-8")
            with patch.object(build, "ROOT", root), patch.dict(os.environ, {"GITHUB_REF_TYPE": "tag", "GITHUB_REF_NAME": "v1.0.1"}):
                self.assertEqual(build.app_version(), "1.0.1")
                with patch.dict(os.environ, {"GITHUB_REF_NAME": "v1.0.0"}):
                    with self.assertRaises(ValueError): build.app_version()

    def test_installer_is_per_user_and_does_not_delete_records(self):
        source = Path("packaging/windows-installer.iss").read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", source)
        self.assertIn(r"DefaultDirName={localappdata}\Programs\MouseActionAssistant", source)
        self.assertIn("recursesubdirs createallsubdirs", source)
        self.assertIn("skipifsilent", source)
        self.assertNotIn("[UninstallDelete]", source)
