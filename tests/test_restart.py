import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app_restart import restart_command, launch_after_exit


class RestartTests(unittest.TestCase):
    def test_frozen_app_relaunches_exact_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "鼠标 助手.app"
            executable = bundle / "Contents/MacOS/鼠标助手"
            executable.parent.mkdir(parents=True)
            (bundle / "Contents/Info.plist").write_text("test")
            with patch.object(sys, "executable", str(executable)), patch.object(sys, "frozen", True, create=True):
                self.assertEqual(restart_command(), ["/usr/bin/open", "-n", str(bundle.resolve())])

    def test_invalid_bundle_is_rejected(self):
        with patch.object(sys, "executable", "/private/tmp/missing-executable"), patch.object(sys, "frozen", True, create=True):
            with self.assertRaises(RuntimeError): restart_command()

    def test_development_relaunch_uses_absolute_script(self):
        with patch.object(sys, "frozen", False, create=True):
            command = restart_command()
            self.assertEqual(Path(command[0]), Path(sys.executable).resolve())
            self.assertTrue(Path(command[1]).is_file())
            self.assertEqual(Path(command[1]).name, "app.py")

    def test_helper_waits_for_old_process_before_launching(self):
        # 仅创建短期测试进程与临时文件，不关闭或重启真实应用。
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "new-process.txt"
            parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
            helper = None
            try:
                command = [sys.executable, "-c",
                           "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('started')", str(marker)]
                helper = launch_after_exit(command, parent.pid)
                time.sleep(0.35)
                self.assertIsNone(helper.poll())
                self.assertFalse(marker.exists())
                parent.terminate(); parent.wait(timeout=3)
                self.assertEqual(helper.wait(timeout=5), 0)
                self.assertEqual(marker.read_text(), "started")
            finally:
                for process in (helper, parent):
                    if process and process.poll() is None:
                        process.terminate(); process.wait(timeout=3)
