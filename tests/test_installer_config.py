import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from scripts import build


class InstallerConfigTests(unittest.TestCase):
    def test_portable_zip_contains_exe_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/"MouseActionAssistant"
            (source/"_internal").mkdir(parents=True)
            (source/"MouseActionAssistant.exe").write_bytes(b"test exe")
            (source/"_internal/runtime.dll").write_bytes(b"test runtime")
            archive = build.build_windows_zip(root)
            with zipfile.ZipFile(archive) as reader:
                self.assertIsNone(reader.testzip())
                self.assertEqual(reader.read("MouseActionAssistant/MouseActionAssistant.exe"), b"test exe")
                self.assertEqual(reader.read("MouseActionAssistant/_internal/runtime.dll"), b"test runtime")
            with self.assertRaises(FileExistsError): build.build_windows_zip(root)

    def test_portable_zip_rejects_incomplete_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeError): build.build_windows_zip(directory)

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
