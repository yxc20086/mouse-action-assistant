"""无全局监听、无真实鼠标注入的回归测试。"""
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.quartz = MagicMock()
        for name in (
            "kCGEventMouseMoved", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp",
            "kCGEventRightMouseDown", "kCGEventRightMouseUp", "kCGEventOtherMouseDown",
            "kCGEventOtherMouseUp", "kCGEventLeftMouseDragged", "kCGEventRightMouseDragged",
            "kCGEventOtherMouseDragged", "kCGMouseButtonLeft", "kCGMouseButtonRight",
            "kCGMouseButtonCenter", "kCGMouseEventClickState", "kCGHIDEventTap",
        ):
            setattr(self.quartz, name, name)
        self.quartz.CGPointMake.side_effect = lambda x, y: (x, y)
        self.quartz.CGEventCreateMouseEvent.side_effect = (
            lambda source, kind, point, button: dict(kind=kind, point=point, button=button))
        self.quartz.CGEventGetLocation.return_value = types.SimpleNamespace(x=100, y=200)
        self.mouse = MagicMock()
        self.modules = patch.dict(sys.modules, {
            "Quartz": self.quartz,
            "pynput": types.SimpleNamespace(mouse=self.mouse, keyboard=MagicMock()),
            "AppKit": MagicMock(),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        module = load_module("engine_test", "engine.py")
        from mouse_backends import MacMouseBackend
        with patch.object(module.MacroEngine, "_init_hotkeys"):
            self.engine = module.MacroEngine(backend=MacMouseBackend())

    def dispatch(self, kind, button="left"):
        self.engine._dispatch_event(dict(type=kind, x=100, y=200, button=button))

    def posted_types(self):
        return [call.args[1]["kind"] for call in self.quartz.CGEventPost.call_args_list]

    def test_buttons_preserve_down_drag_up(self):
        for button, prefix in [("left", "Left"), ("right", "Right"), ("middle", "Other")]:
            with self.subTest(button=button):
                self.quartz.CGEventPost.reset_mock()
                self.dispatch("click_down", button)
                self.assertIn(button, self.engine._pressed_buttons)
                self.assertEqual(len(self.posted_types()), 1)
                self.dispatch("move")
                self.dispatch("click_up", button)
                self.assertEqual(self.posted_types(), [
                    f"kCGEvent{prefix}MouseDown", f"kCGEvent{prefix}MouseDragged",
                    f"kCGEvent{prefix}MouseUp"])
                self.assertFalse(self.engine._pressed_buttons)

    def test_unpaired_up_is_ignored(self):
        self.dispatch("click_up")
        self.quartz.CGEventPost.assert_not_called()

    def test_legacy_control_metadata_does_not_change_coordinate_replay(self):
        # 历史试验记录仍保留坐标，附加元数据不应再触发控件动作。
        for kind in ("click_down", "click_up"):
            self.engine._dispatch_event({"type": kind, "x": 100, "y": 200,
                                         "button": "left", "ax_target": {"action": "AXPress"}})
        self.assertEqual(self.posted_types(), ["kCGEventLeftMouseDown", "kCGEventLeftMouseUp"])
        self.assertFalse(self.engine._pressed_buttons)

    def test_release_only_held_buttons(self):
        self.engine._safety_release()
        self.quartz.CGEventPost.assert_not_called()
        self.dispatch("click_down", "right")
        self.engine._safety_release()
        self.assertEqual(self.posted_types(), ["kCGEventRightMouseDown", "kCGEventRightMouseUp"])
        self.assertFalse(self.engine._pressed_buttons)

    def test_post_failure_is_not_silenced(self):
        self.quartz.CGEventPost.side_effect = RuntimeError("failed")
        with self.assertRaises(RuntimeError):
            self.dispatch("click_down")

    def test_countdown_can_stop_without_posting_clicks(self):
        self.engine.events = [dict(type="click_down", time=0, x=100, y=200, button="left")]
        self.engine.on_state_change = MagicMock()
        self.engine._sleep_interruptible = MagicMock(return_value=False)
        self.engine._run_playback_thread(1, 1, 3, 0)
        self.engine.on_state_change.assert_any_call("COUNTDOWN", {"seconds": 3})
        self.quartz.CGEventPost.assert_not_called()
        self.assertEqual(self.engine.state, "IDLE")

    def test_corner_failsafe_still_interrupts_wait(self):
        self.engine._check_corner_failsafe = MagicMock(return_value=True)
        self.assertFalse(self.engine._sleep_interruptible(1))
        self.assertTrue(self.engine._abort_requested)

    def test_recording_keeps_click_pair_and_summary(self):
        self.engine.state = "RECORDING"
        self.engine._on_mouse_click(100, 200, self.mouse.Button.right, True, False)
        self.engine._on_mouse_click(100, 200, self.mouse.Button.right, False, False)
        self.assertEqual([e["type"] for e in self.engine.events], ["click_down", "click_up"])
        self.assertEqual(self.engine.get_summary()["click_count"], 1)

    def test_incomplete_track_releases_each_loop(self):
        self.engine.events = [dict(type="click_down", x=100, y=200, button="left", time=0)]
        self.engine._run_playback_thread(2, 1, 0, 0)
        self.assertEqual(self.posted_types(), ["kCGEventLeftMouseDown", "kCGEventLeftMouseUp"] * 2)
        self.assertEqual(self.engine.state, "IDLE")

    def test_double_click_count_matches_on_release(self):
        for _ in range(2):
            self.dispatch("click_down")
            self.dispatch("click_up")
        self.assertEqual([c.args[2] for c in self.quartz.CGEventSetIntegerValueField.call_args_list],
                         [1, 1, 2, 2])

    def test_fast_moves_are_not_dropped(self):
        self.engine.state = "RECORDING"
        with patch("time.perf_counter", return_value=0.001):
            for i in range(10000):
                self.engine._on_mouse_move(i, i)
        self.assertEqual(len(self.engine.events), 10000)
        self.assertEqual(self.engine.events[-1]["x"], 9999)

    def test_slow_ui_never_runs_inside_recorder(self):
        fake_engine_module = types.SimpleNamespace(MacroEngine=MagicMock())
        with patch.dict(sys.modules, {"engine": fake_engine_module, "webview": MagicMock()}):
            api_module = load_module("api_test", "api.py")
        api = api_module.JsBridgeAPI()
        api.window = MagicMock()
        api.window.evaluate_js.side_effect = AssertionError("不允许同步等待 UI")
        api.engine = self.engine
        self.engine.on_event_broadcast = api._on_event_broadcast
        self.engine.state = "RECORDING"
        for i in range(10000):
            self.engine._on_mouse_move(i, i)
            if i % 100 == 0:
                self.engine._on_mouse_click(i, i, self.mouse.Button.left, True)
                self.engine._on_mouse_click(i, i, self.mouse.Button.left, False)
        self.assertEqual(len(self.engine.events), 10200)
        self.assertEqual(self.engine.get_summary()["click_count"], 100)
        self.assertLessEqual(len(api._updates), 4096)
        api._on_state_change("IDLE", {"summary": self.engine.get_summary()})
        received = []
        while api._updates:
            received.extend(api.get_updates())
        self.assertEqual(received[-1]["state"], "IDLE")
        self.assertEqual(len(api.get_track_snapshot()["events"]), 10200)
        api.window.evaluate_js.assert_not_called()

    def test_dead_listener_reports_incomplete_recording(self):
        listener = MagicMock()
        listener.is_alive.return_value = False
        listener.join.side_effect = RuntimeError("callback failed")
        self.engine.state = "RECORDING"
        self.engine._mouse_listener = listener
        self.engine.recording_diagnostics = {"samples": []}
        self.engine.on_state_change = MagicMock()
        with patch("time.sleep"):
            self.engine._watch_recording(listener)
        self.assertEqual(self.engine.state, "IDLE")
        args = self.engine.on_state_change.call_args.args
        self.assertEqual(args[0], "ERROR")
        self.assertIn("callback failed", args[1]["message"])

    def test_diagnostics_capture_pointer_without_recorded_events(self):
        import json
        listener = MagicMock()
        listener.is_alive.return_value = True
        self.quartz.CGEventGetLocation.return_value = types.SimpleNamespace(x=360.3, y=453.8)
        self.quartz.CGEventSourceButtonState.return_value = False
        sys.modules["AppKit"].NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value.bundleIdentifier.return_value = "com.apple.finder"
        sample = self.engine._diagnostic_sample(listener)
        self.assertEqual(sample["event_count"], 0)
        self.assertEqual(sample["pointer"], [360.3, 453.8])
        self.assertEqual(sample["frontmost_app"], "com.apple.finder")
        self.assertTrue(sample["listener_alive"])
        json.dumps(sample)

    def test_stop_during_press_releases_button(self):
        self.engine.events = [
            dict(type="click_down", time=0, x=100, y=200, button="left"),
            dict(type="click_up", time=1, x=100, y=200, button="left"),
        ]
        self.engine.on_event_broadcast = lambda _: self.engine.stop_playback()
        self.engine._run_playback_thread(1, 1, 0, 0)
        self.assertEqual(self.posted_types(), ["kCGEventLeftMouseDown", "kCGEventLeftMouseUp"])
        self.assertFalse(self.engine._pressed_buttons)


class PermissionTests(unittest.TestCase):
    def test_detection_error_denies_access(self):
        module = load_module("permission_test", "permission_checker.py")
        with patch.object(module.sys, "platform", "darwin"), patch.object(module.ctypes.cdll, "LoadLibrary", side_effect=OSError):
            self.assertFalse(module.is_accessibility_trusted())

    def test_listener_does_not_grant_post_permission(self):
        module = load_module("permission_test", "permission_checker.py")
        library = MagicMock()
        library.AXIsProcessTrusted.return_value = False
        with patch.object(module.sys, "platform", "darwin"), patch.object(module.ctypes.cdll, "LoadLibrary", return_value=library):
            self.assertFalse(module.is_accessibility_trusted())


if __name__ == "__main__":
    unittest.main()
