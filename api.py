"""
Web 与 Python 双向交互桥梁 API (JsBridgeAPI)
"""
import json
import os
import threading
from collections import deque
from typing import Dict, Optional
import webview
from engine import MacroEngine
from permission_checker import is_accessibility_trusted, open_accessibility_settings
from record_store import RecordStore, validate_events
from app_restart import restart_command, launch_after_exit


class JsBridgeAPI:
    def __init__(self, record_directory=None):
        self.window: Optional[webview.Window] = None
        self._auto_minimized = False
        self._updates = deque()
        self._updates_lock = threading.Lock()
        self._record_lock = threading.RLock()
        self._was_recording = False
        self.store = RecordStore(record_directory)
        self.selected_record_id = None
        self._restart_pending = False
        self._restart_helper = None
        self.engine = MacroEngine(
            on_event_broadcast=self._on_event_broadcast,
            on_state_change=self._on_state_change,
        )
        records = self.store.list()
        if records:
            self.select_record(records[0]["id"])

    def set_window(self, window: webview.Window):
        self.window = window

    def _on_event_broadcast(self, event_data: Dict):
        # 这里运行在系统鼠标监听/回放线程，绝不能等待 WebKit。
        # 只允许预览丢帧；完整轨迹始终保存在 engine.events 中。
        with self._updates_lock:
            if len(self._updates) < 4096:
                self._updates.append({"event": event_data})

    def _on_state_change(self, state: str, data: Dict):
        with self._record_lock:
            if state == "RECORDING":
                self._was_recording = True
            elif state == "IDLE" and self._was_recording:
                self._was_recording = False
                if self.engine.events:
                    record = self.store.add(self.engine.events, self.engine.recording_diagnostics)
                    self.selected_record_id = record["id"]
                    if not record["saved"]:
                        data = dict(data, warning="自动保存失败，记录暂存于内存；请退出前导出文件。")
                elif self.selected_record_id:
                    self.select_record(self.selected_record_id)
        # 统一处理按钮和全局快捷键启动，只有通过权限检查进入录制后才最小化。
        if state == "RECORDING" and self.window and not self._auto_minimized:
            try:
                self.window.minimize()
                self._auto_minimized = True
            except Exception as e:
                data = dict(data, warning=f"录制已开始，但窗口最小化失败：{e}")
        if state == "IDLE" and self._auto_minimized:
            self._auto_minimized = False
            if self.window:
                try:
                    self.window.restore()
                except Exception as e:
                    print(f"自愈还原窗口异常: {e}")

        with self._updates_lock:
            if state == "RECORDING":
                self._updates.clear()
            self._updates.append({"state": state, "data": data})

    def get_updates(self):
        """由界面批量拉取，最小化或界面卡顿不阻塞录制。"""
        with self._updates_lock:
            batch = [self._updates.popleft() for _ in range(min(512, len(self._updates)))]
        return batch

    def get_track_snapshot(self):
        return {"events": list(self.engine.events), "summary": self.engine.get_summary()}

    # ---------------- 前端调用的接口 ----------------
    def get_records(self):
        with self._record_lock:
            return {"records": self.store.list(), "selected_id": self.selected_record_id,
                    "state": self.engine.state, "summary": self.engine.get_summary(),
                    "warnings": self.store.warnings}

    def select_record(self, record_id):
        with self._record_lock:
            if self.engine.state != "IDLE":
                return {"success": False, "error": "请先停止录制或回放，再切换记录"}
            try:
                record = self.store.get(record_id)
                self.engine.events = record["events"]
                self.engine.recording_diagnostics = record["diagnostics"]
                self.selected_record_id = record_id
                return {"success": True, "summary": self.engine.get_summary()}
            except ValueError as error:
                return {"success": False, "error": str(error)}

    def start_recording(self):
        with self._record_lock:
            return self.engine.start_recording()

    def rename_record(self, record_id, name):
        with self._record_lock:
            if self.engine.state != "IDLE":
                return {"success": False, "error": "请先停止录制或回放，再修改名称"}
            try:
                self.store.rename(record_id, name)
                return {"success": True}
            except (ValueError, OSError) as error:
                return {"success": False, "error": f"名称未修改：{error}"}

    def stop_recording(self):
        if self.engine.state == "RECORDING":
            self.engine.stop_recording()

    def delete_record(self, record_id):
        with self._record_lock:
            if self.engine.state != "IDLE" or self._was_recording:
                return {"success": False, "error": "请先停止录制或回放，再删除记录"}
            try:
                result = self.store.delete(record_id)
                if self.selected_record_id == record_id:
                    records = self.store.list()
                    if records:
                        self.select_record(records[0]["id"])
                    else:
                        self.selected_record_id = None
                        self.engine.events = []
                        self.engine.recording_diagnostics = {}
                return {"success": True, **result}
            except (ValueError, OSError) as error:
                return {"success": False, "error": f"删除失败：{error}"}

    def restart_app(self):
        with self._record_lock:
            if self._restart_pending:
                return {"success": False, "error": "正在重启，请稍候"}
            if self.engine.state != "IDLE" or self._was_recording:
                return {"success": False, "error": "请先停止录制或回放，再重启应用"}
            if not self.window:
                return {"success": False, "error": "应用窗口尚未就绪"}
            if any(not record["saved"] for record in self.store.list()):
                return {"success": False, "error": "存在未自动保存的记录，已取消重启。请先导出备份并处理存储问题"}
            try:
                self._restart_pending = True
                self.engine.state = "RESTARTING"
                self._restart_helper = launch_after_exit(restart_command())
                timer = threading.Timer(0.3, self._close_for_restart)
                timer.daemon = True
                timer.start()
            except Exception as error:
                self._cancel_restart()
                return {"success": False, "error": f"未能安排重启：{error}"}
            return {"success": True}

    def _cancel_restart(self):
        if self._restart_helper and self._restart_helper.poll() is None:
            self._restart_helper.terminate()
        self._restart_helper = None
        self._restart_pending = False
        self.engine.state = "IDLE"

    def _close_for_restart(self):
        try:
            self.window.destroy()
            # 关闭窗口是异步的；若未关闭则保留应用并取消重启，避免无限等待。
            if not self.window.events.closed.wait(5):
                raise RuntimeError("窗口未能关闭，请稍后重试")
        except Exception as error:
            with self._record_lock:
                self._cancel_restart()
                self._on_state_change("ERROR", {"message": f"重启取消：{error}"})

    def start_playback(self, config: Dict) -> Dict:
        with self._record_lock:
            record_id = config.get("record_id", self.selected_record_id)
            if not record_id:
                return {"success": False, "error": "请先选择一条录制记录"}
            result = self.select_record(record_id)
            if not result["success"]:
                return result
            return self._start_selected_playback(config)

    def _start_selected_playback(self, config):
        auto_min = config.get("auto_minimize", True)
        if auto_min and self.window:
            try:
                self._auto_minimized = True
                self.window.minimize()
                import time
                time.sleep(0.18)
            except Exception as e:
                print(f"最小化窗口异常: {e}")
        result = self.engine.start_playback(config)
        if not result.get("success") and self._auto_minimized and self.window:
            self._auto_minimized = False
            self.window.restore()
        return result

    def stop_playback(self):
        self.engine.stop_playback()
        if self._auto_minimized and self.window:
            self._auto_minimized = False
            try:
                self.window.restore()
            except Exception as e:
                print(f"急停还原窗口异常: {e}")

    def get_permission_status(self) -> bool:
        return is_accessibility_trusted(prompt_user=False)

    def get_permissions(self):
        return self.engine._diagnostic_permissions()

    def open_input_settings(self):
        import subprocess
        subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"], check=False)

    def open_permission_settings(self):
        # 尝试触发系统自带授权弹窗
        is_accessibility_trusted(prompt_user=True)
        # 同时打开系统设置面板
        open_accessibility_settings()

    def reset_permission_cache(self) -> bool:
        """重置过期的 TCC 权限记录，并打开系统设置引导用户重新授权"""
        from permission_checker import reset_accessibility_cache
        reset_accessibility_cache()
        open_accessibility_settings()
        return True

    def get_screen_size(self) -> Dict[str, int]:
        return self.engine.get_screen_size()

    def save_track_file(self) -> bool:
        if not self.window or not self.engine.events or self.engine.state != "IDLE":
            return False
        events = list(self.engine.events)
        diagnostics = dict(self.engine.recording_diagnostics)
        result = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename="mouse_track.json",
            file_types=("JSON Files (*.json)",),
        )
        if result:
            save_path = result if isinstance(result, str) else result[0]
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(events, f, indent=2, ensure_ascii=False)
            if diagnostics:
                diagnostic_path = os.path.splitext(save_path)[0] + ".diagnostics.json"
                with open(diagnostic_path, "w", encoding="utf-8") as f:
                    json.dump(diagnostics, f, indent=2, ensure_ascii=False)
            return True
        return False

    def load_track_file(self) -> Dict:
        if not self.window or self.engine.state != "IDLE":
            return {"success": False}
        result = self.window.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("JSON Files (*.json)",),
        )
        if result:
            load_path = result[0] if isinstance(result, (list, tuple)) else result
            try:
                with open(load_path, "r", encoding="utf-8") as f:
                    events = json.load(f)
                validate_events(events)
                with self._record_lock:
                    if self.engine.state != "IDLE":
                        return {"success": False, "error": "操作进行中，暂时不能导入"}
                    record = self.store.add(events, name=os.path.splitext(os.path.basename(load_path))[0])
                    result = self.select_record(record["id"])
                    if not record["saved"]:
                        result["warning"] = "导入的记录暂存于内存，自动保存失败。"
                    return result
            except Exception as e:
                return {"success": False, "error": f"导入失败：{e}"}
        return {"success": False}

    def clear_track(self):
        if self.engine.state != "IDLE":
            return
        self.engine.events = []
        self.engine.recording_diagnostics = {}
