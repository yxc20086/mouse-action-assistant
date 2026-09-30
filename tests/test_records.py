import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
import types

from record_store import RecordStore, validate_events
from test_engine import load_module


def track(x=10):
    return [dict(type="click_down", time=0, x=x, y=20, button="left"),
            dict(type="click_up", time=0.1, x=x, y=20, button="left")]


class RecordStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_multiple_records_survive_restart(self):
        store = RecordStore(self.directory)
        a = store.add(track(10)); b = store.add(track(30))
        self.assertNotEqual(a["id"], b["id"])
        restored = RecordStore(self.directory)
        self.assertEqual(len(restored.list()), 2)
        self.assertEqual(restored.get(a["id"])["events"][0]["x"], 10)
        self.assertEqual(restored.get(b["id"])["events"][0]["x"], 30)

    def test_selected_copy_cannot_modify_saved_track(self):
        store = RecordStore(self.directory); events = track()
        record = store.add(events)
        events[0]["x"] = 99
        copy = store.get(record["id"]); copy["events"][0]["x"] = 88
        self.assertEqual(store.get(record["id"])["events"][0]["x"], 10)

    def test_corrupt_record_is_preserved_and_reported(self):
        file = self.directory / "broken.json"
        file.write_text("bad json")
        store = RecordStore(self.directory)
        self.assertTrue(file.exists()); self.assertEqual(len(store.warnings), 1)

    def test_save_failure_retains_memory_record(self):
        store = RecordStore(self.directory)
        with patch("record_store.os.replace", side_effect=OSError("disk full")):
            record = store.add(track())
        self.assertFalse(record["saved"])
        self.assertEqual(len(store.list()), 1)
        self.assertEqual(store.get(record["id"])["events"], track())

    def test_invalid_import_rejected(self):
        for invalid in ({}, [], [dict(type="bad")], [dict(type="move", time=float("nan"), x=1, y=1)]):
            with self.assertRaises(ValueError): validate_events(invalid)

    def test_delete_survives_restart_and_preserves_recovery_copy(self):
        store = RecordStore(self.directory)
        deleted = store.add(track(10)); kept = store.add(track(20))
        self.assertTrue(store.delete(deleted["id"])["recoverable"])
        self.assertEqual([r["id"] for r in RecordStore(self.directory).list()], [kept["id"]])
        copies = list((self.directory / ".trash").glob("*.json"))
        self.assertEqual(len(copies), 1)
        self.assertEqual(json.loads(copies[0].read_text())["events"], track(10))

    def test_delete_failure_keeps_record(self):
        store = RecordStore(self.directory); record = store.add(track())
        with patch("record_store.os.replace", side_effect=OSError("read only")):
            with self.assertRaises(OSError): store.delete(record["id"])
        self.assertEqual(store.get(record["id"])["events"], track())
        self.assertTrue((self.directory / (record["id"] + ".json")).exists())

    def test_unknown_delete_is_rejected(self):
        store = RecordStore(self.directory)
        with self.assertRaises(ValueError): store.delete("../outside")

    def test_legacy_record_keeps_coordinates_and_metadata(self):
        events = track()
        events[0]["ax_target"] = {"action": "AXPress", "bundle_id": "com.microsoft.VSCode"}
        store = RecordStore(self.directory)
        record = store.add(events)
        restored = RecordStore(self.directory).get(record["id"])
        self.assertEqual(restored["events"], events)

    def test_rename_persists_without_changing_time_or_events(self):
        store = RecordStore(self.directory)
        record = store.add(track(), {"started_at": "2026-09-30T11:09:51+0800"})
        store.rename(record["id"], "  Chrome 菜单操作  ")
        restored = RecordStore(self.directory).get(record["id"])
        self.assertEqual(restored["name"], "Chrome 菜单操作")
        self.assertEqual(restored["created_at"], record["created_at"])
        self.assertEqual(restored["events"], record["events"])
        self.assertEqual(store.list()[0]["recorded_at"], "2026-09-30T11:09:51+08:00")

    def test_rename_failure_preserves_original(self):
        store = RecordStore(self.directory); record = store.add(track())
        for invalid in ("", "  ", "x" * 81, "a\nb"):
            with self.assertRaises(ValueError): store.rename(record["id"], invalid)
        with patch("record_store.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): store.rename(record["id"], "new")
        self.assertEqual(store.get(record["id"])["name"], record["name"])
        self.assertEqual(RecordStore(self.directory).get(record["id"])["name"], record["name"])


class BridgeRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        fake = MagicMock(); fake.state = "IDLE"; fake.events = []; fake.recording_diagnostics = {}
        fake.get_summary.side_effect = lambda: {"total_events": len(fake.events), "click_count": len(fake.events)//2, "duration": 0.1}
        with patch.dict(sys.modules, {"engine": types.SimpleNamespace(MacroEngine=MagicMock(return_value=fake)), "webview": MagicMock()}):
            self.module = load_module("record_api_test", "api.py")
        self.api = self.module.JsBridgeAPI(self.temp.name)
        self.engine = fake

    def record(self, x):
        self.engine.state = "RECORDING"
        self.api._on_state_change("RECORDING", {})
        self.engine.events = track(x)
        self.engine.state = "IDLE"
        self.api._on_state_change("IDLE", {})
        return self.api.selected_record_id

    def test_stop_adds_once_and_selection_restores_events(self):
        first = self.record(10); second = self.record(30)
        self.api._on_state_change("IDLE", {})  # 回放结束不能再生成记录
        self.assertEqual(len(self.api.get_records()["records"]), 2)
        self.assertTrue(self.api.select_record(first)["success"])
        self.assertEqual(self.engine.events[0]["x"], 10)
        self.assertNotEqual(first, second)

    def test_record_start_minimizes_and_stop_restores_once(self):
        self.api.window = MagicMock()
        self.record(10)
        self.api.window.minimize.assert_called_once()
        self.api.window.restore.assert_called_once()
        self.assertFalse(self.api._auto_minimized)
        self.api._on_state_change("IDLE", {})
        self.api.window.restore.assert_called_once()

    def test_permission_denied_does_not_minimize(self):
        self.api.window = MagicMock()
        self.api._on_state_change("PERMISSION_DENIED", {})
        self.api.window.minimize.assert_not_called()

    def test_minimize_failure_does_not_break_recording(self):
        self.api.window = MagicMock()
        self.api.window.minimize.side_effect = RuntimeError("window unavailable")
        self.record(10)
        self.assertEqual(len(self.api.get_records()["records"]), 1)
        self.api.window.restore.assert_not_called()
        self.assertTrue(any("warning" in item.get("data", {}) for item in self.api.get_updates()))

    def test_playback_uses_requested_record(self):
        first = self.record(10); self.record(30)
        self.engine.start_playback.return_value = {"success": True}
        self.assertTrue(self.api.start_playback({"record_id": first, "auto_minimize": False})["success"])
        self.assertEqual(self.engine.events[0]["x"], 10)
        self.engine.start_playback.assert_called_once()

    def test_restart_refuses_active_operation_and_unsaved_records(self):
        self.api.window = MagicMock()
        with patch.object(self.module, "launch_after_exit") as launch:
            for state in ("RECORDING", "COUNTDOWN", "PLAYING"):
                self.engine.state = state
                self.assertFalse(self.api.restart_app()["success"])
            self.engine.state = "IDLE"
            with patch("record_store.os.replace", side_effect=OSError("disk full")):
                self.api.store.add(track())
            result = self.api.restart_app()
            self.assertFalse(result["success"])
            self.assertIn("未自动保存", result["error"])
            launch.assert_not_called()
            self.api.window.destroy.assert_not_called()

    def test_restart_schedules_one_relaunch_and_keeps_records(self):
        self.record(10)
        self.api.window = MagicMock()
        with patch.object(self.module, "launch_after_exit") as launch, patch.object(self.module.threading, "Timer") as timer:
            self.assertTrue(self.api.restart_app()["success"])
            self.assertEqual(self.engine.state, "RESTARTING")
            self.assertFalse(self.api.restart_app()["success"])
            launch.assert_called_once()
            timer.return_value.start.assert_called_once()
            self.api.window.destroy.assert_not_called()
            self.api._close_for_restart()
            self.api.window.destroy.assert_called_once()
            self.assertEqual(len(RecordStore(self.temp.name).list()), 1)

    def test_restart_launch_failure_keeps_window(self):
        self.api.window = MagicMock()
        with patch.object(self.module, "launch_after_exit", side_effect=OSError("launch failed")):
            self.assertFalse(self.api.restart_app()["success"])
        self.api.window.destroy.assert_not_called()
        self.assertFalse(self.api._restart_pending)
        self.assertEqual(self.engine.state, "IDLE")

    def test_failed_window_close_cancels_helper(self):
        self.api.window = MagicMock()
        self.api.window.events.closed.wait.return_value = False
        helper = MagicMock(); helper.poll.return_value = None
        with patch.object(self.module, "launch_after_exit", return_value=helper), patch.object(self.module.threading, "Timer"):
            self.assertTrue(self.api.restart_app()["success"])
            self.api._close_for_restart()
        helper.terminate.assert_called_once()
        self.assertFalse(self.api._restart_pending)
        self.assertEqual(self.engine.state, "IDLE")

    def test_cannot_switch_while_playing_or_recording(self):
        first = self.record(10); self.record(30)
        for state in ("PLAYING", "COUNTDOWN", "RECORDING"):
            self.engine.state = state
            self.assertFalse(self.api.select_record(first)["success"])
            self.assertEqual(self.engine.events[0]["x"], 30)

    def test_delete_selection_and_last_record(self):
        first = self.record(10); second = self.record(20)
        self.assertTrue(self.api.delete_record(second)["success"])
        self.assertEqual(self.api.selected_record_id, first)
        self.assertEqual(self.engine.events, track(10))
        self.assertTrue(self.api.delete_record(first)["success"])
        self.assertIsNone(self.api.selected_record_id)
        self.assertEqual(self.engine.events, [])
        self.assertEqual(self.engine.recording_diagnostics, {})

    def test_delete_unselected_preserves_selection(self):
        first = self.record(10); second = self.record(20)
        self.assertTrue(self.api.delete_record(first)["success"])
        self.assertEqual(self.api.selected_record_id, second)

    def test_delete_blocked_during_operations(self):
        record_id = self.record(10)
        for state in ("RECORDING", "COUNTDOWN", "PLAYING", "RESTARTING"):
            self.engine.state = state
            self.assertFalse(self.api.delete_record(record_id)["success"])
        self.assertEqual(len(self.api.store.list()), 1)

    def test_export_keeps_legacy_array_and_diagnostic_sidecar(self):
        self.record(10)
        self.engine.recording_diagnostics = {"samples": []}
        self.api.window = MagicMock()
        target = str(Path(self.temp.name) / "export.json")
        self.api.window.create_file_dialog.return_value = target
        self.assertTrue(self.api.save_track_file())
        self.assertEqual(json.loads(Path(target).read_text()), track(10))
        self.assertTrue(Path(self.temp.name, "export.diagnostics.json").exists())
