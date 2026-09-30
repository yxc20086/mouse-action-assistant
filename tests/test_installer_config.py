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
        source = Path("packaging/windows-installer.nsi").read_text(encoding="utf-8")
        self.assertIn("RequestExecutionLevel user", source)
        self.assertIn(r'InstallDir "$LOCALAPPDATA\Programs\MouseActionAssistant"', source)
        self.assertIn('!include "${UNINSTALL_FILES}"', source)
        self.assertNotIn("RMDir /r", source)

    def test_uninstall_manifest_removes_only_packaged_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"_internal").mkdir()
            (root/"_internal/test$file.txt").write_text("data")
            manifest = build.uninstall_manifest(root)
            self.assertIn(r'Delete "$INSTDIR\_internal\test$$file.txt"', manifest)
            self.assertIn(r'RMDir "$INSTDIR\_internal"', manifest)
            self.assertNotIn("/r", manifest)
            self.assertNotIn("*", manifest)
