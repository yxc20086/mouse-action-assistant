import ctypes
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from windows_mouse import WindowsMouseBackend, INPUT, MOUSEINPUT, POINT
from platform_support import recordings_directory, configure_dpi
import permission_checker


class WindowsBackendTests(unittest.TestCase):
    def setUp(self):
        self.api = MagicMock()
        self.api.GetSystemMetrics.side_effect = {76:-1920, 77:-200, 78:3840, 79:1280}.__getitem__
        self.events = []
        def send(count, pointer, size):
            self.events.append(INPUT.from_buffer_copy(ctypes.string_at(pointer, size)))
            return count
        self.api.SendInput.side_effect = send
        self.backend = WindowsMouseBackend(self.api)

    def test_win64_input_layout(self):
        self.assertEqual(ctypes.sizeof(MOUSEINPUT), 32 if ctypes.sizeof(ctypes.c_void_p)==8 else 24)
        self.assertEqual(ctypes.sizeof(INPUT), 40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)

    def test_negative_screen_coordinates_and_flags(self):
        self.backend.move(-1920, -200, set())
        event = self.events[-1]
        self.assertEqual(event.type, 0)
        self.assertEqual(event.mi.dwFlags, 0xc001)
        self.assertLess(event.mi.dx, 30)
        self.assertLess(event.mi.dy, 30)
        self.backend.move(1919, 1079, set())
        self.assertGreater(self.events[-1].mi.dx, 65500)

    def test_every_button_and_scroll(self):
        for name, flags in self.backend.BUTTONS.items():
            self.backend.button(10, 10, name, True)
            self.backend.button(10, 10, name, False)
            self.assertEqual(self.events[-2].mi.dwFlags, 0xc001 | flags[0])
            self.assertEqual(self.events[-1].mi.dwFlags, 0xc001 | flags[1])
        self.backend.scroll(10, 10, -1, -2)
        self.assertEqual(self.events[-2].mi.dwFlags, 0x0800)
        self.assertEqual(self.events[-2].mi.mouseData, (-240) & 0xffffffff)
        self.assertEqual(self.events[-1].mi.dwFlags, 0x1000)

    def test_sendinput_failure_is_reported(self):
        self.api.SendInput.side_effect = lambda *_: 0
        with self.assertRaisesRegex(RuntimeError, "Windows"):
            self.backend.button(10, 10, "left", True)

    def test_outside_desktop_rejected(self):
        with self.assertRaises(ValueError): self.backend.move(9999, 0, set())
        self.api.SendInput.assert_not_called()

    def test_windows_paths_and_permission_model(self):
        with patch.object(sys, "platform", "win32"), patch.dict(os.environ, {"LOCALAPPDATA": str(Path.home()/"test-local")}):
            self.assertEqual(recordings_directory(), Path.home()/"test-local/MouseActionAssistant/recordings")
            status = permission_checker.get_permission_status()
            self.assertEqual(status["platform"], "windows")
            self.assertFalse(status["requires_permissions"])

    def test_dpi_setup_before_gui(self):
        dll = MagicMock()
        with patch.object(sys, "platform", "win32"), patch.object(ctypes, "WinDLL", return_value=dll, create=True):
            configure_dpi()
        self.assertEqual(dll.SetProcessDpiAwarenessContext.call_args.args[0].value, ctypes.c_void_p(-4).value)
