"""
现代化鼠标动作录制与回放核心引擎 (MacroEngine)
具备双重急停机制（Esc 物理键 + 屏幕左上角物理甩动 Fail-Safe）、微秒级相对时序还原与实时事件广播。
"""
import json
import os
import sys
import threading
import time
from typing import Callable, Dict, List, Optional
import Quartz
from pynput import keyboard, mouse

class MacroEngine:
    def __init__(self, on_event_broadcast: Optional[Callable[[Dict], None]] = None,
                 on_state_change: Optional[Callable[[str, Dict], None]] = None):
        self.on_event_broadcast = on_event_broadcast
        self.on_state_change = on_state_change

        self.state: str = "IDLE"  # "IDLE" | "RECORDING" | "COUNTDOWN" | "PLAYING"
        self.events: List[Dict] = []
        self.recording_diagnostics = {}
        self._record_start_time: float = 0.0
        self._last_move_time: float = 0.0
        self._last_pos = (None, None)

        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._player_thread: Optional[threading.Thread] = None
        self._abort_requested: bool = False
        self._corner_hit_count: int = 0
        self._play_start_time: float = 0.0

        # 按键状态与硬件事件源（彻底解决点击丢失与拖拽冲突问题）
        self._pressed_buttons = set()
        self._button_click_counts = {}
        self._last_click_down_time: float = 0.0
        self._last_click_pos = (0, 0)
        self._last_click_time: float = 0.0
        self._click_count: int = 1
        try:
            self._event_source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        except Exception:
            self._event_source = None

        self.mouse_controller = mouse.Controller()

        # 启动全局快捷键监听
        self._init_hotkeys()

    def get_screen_size(self) -> Dict[str, int]:
        """与鼠标事件一致的桌面逻辑坐标范围（包括副屏）。"""
        try:
            error, displays, count = Quartz.CGGetActiveDisplayList(32, None, None)
            if error or not count:
                raise RuntimeError("无法读取显示器")
            bounds = [Quartz.CGDisplayBounds(d) for d in displays[:count]]
            x = min(b.origin.x for b in bounds)
            y = min(b.origin.y for b in bounds)
            right = max(b.origin.x + b.size.width for b in bounds)
            bottom = max(b.origin.y + b.size.height for b in bounds)
            return {"x": x, "y": y, "width": right - x, "height": bottom - y}
        except Exception:
            return {"width": 1710, "height": 1107}


    def _init_hotkeys(self):
        """配置全局快捷键与急停侦测"""
        ctrl_keys = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
        self._ctrl_pressed = False

        def on_press(key):
            try:
                if key in ctrl_keys:
                    self._ctrl_pressed = True

                # 1. 紧急急停：随时按下 Esc 键
                if key == keyboard.Key.esc:
                    if self.state in ("COUNTDOWN", "PLAYING"):
                        self.stop_playback()
                    return

                # 2. 录制切换：F7 或 Ctrl+R
                if key == keyboard.Key.f7 or (
                    self._ctrl_pressed and hasattr(key, 'char') and key.char in ('r', 'R')
                ):
                    self.toggle_recording()
                    return

                # 3. 回放切换：F8 或 Ctrl+P
                if key == keyboard.Key.f8 or (
                    self._ctrl_pressed and hasattr(key, 'char') and key.char in ('p', 'P')
                ):
                    self.toggle_playback()
                    return
            except Exception:
                pass

        def on_release(key):
            if key in ctrl_keys:
                self._ctrl_pressed = False

        self._keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._keyboard_listener.daemon = True
        self._keyboard_listener.start()

    # ---------------- 录制逻辑 ----------------
    def start_recording(self):
        if self.state != "IDLE":
            return {"success": False, "error": "请先停止当前操作"}
        from permission_checker import is_accessibility_trusted
        if not is_accessibility_trusted():
            if self.on_state_change:
                self.on_state_change("PERMISSION_DENIED", {})
            return {"success": False, "error": "请先授权当前应用的辅助功能权限"}
        if self._diagnostic_permissions().get("listen_events") is not True:
            if self.on_state_change:
                self.on_state_change("PERMISSION_DENIED", {})
            return {"success": False, "error": "输入监控未就绪，请为当前应用授权并重启后录制"}
        if not self._keyboard_listener or not self._keyboard_listener.is_alive():
            self._init_hotkeys()
        # 强制清理可能残留的旧监听器
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

        self.events = []
        self.state = "RECORDING"
        self._record_start_time = time.perf_counter()
        self._last_move_time = self._record_start_time
        self._last_pos = (None, None)
        self.recording_diagnostics = {
            "version": "diagnostic-v3",
            "executable": sys.executable,
            "pid": os.getpid(),
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "permissions": self._diagnostic_permissions(),
            "samples": [],
        }

        if self.on_state_change:
            self.on_state_change("RECORDING", {})

        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._mouse_listener.daemon = True
        self._mouse_listener.start()
        threading.Thread(target=self._watch_recording, args=(self._mouse_listener,), daemon=True).start()
        return {"success": True}

    def _watch_recording(self, listener):
        while self.state == "RECORDING" and self._mouse_listener is listener:
            time.sleep(0.25)
            if self.state != "RECORDING" or self._mouse_listener is not listener:
                return
            self.recording_diagnostics["samples"].append(self._diagnostic_sample(listener))
            if not listener.is_alive():
                message = "鼠标监听已中断，当前轨迹可能不完整。请检查当前 App 的辅助功能/输入监控权限并重新录制。"
                try:
                    listener.join(timeout=0)
                except Exception as e:
                    message += f" 错误：{e}"
                self.stop_recording()
                if self.on_state_change:
                    self.on_state_change("ERROR", {"message": message})
                return

    def _diagnostic_permissions(self):
        from permission_checker import is_accessibility_trusted
        result = {"accessibility": is_accessibility_trusted()}
        for key, name in [("listen_events", "CGPreflightListenEventAccess"),
                          ("post_events", "CGPreflightPostEventAccess")]:
            try:
                result[key] = bool(getattr(Quartz, name)())
            except Exception as e:
                result[key] = {"error": str(e)}
        return result

    def _diagnostic_sample(self, listener):
        # 独立于事件回调的只读采样，不注入事件，不收集按键、窗口标题或网页内容。
        sample = {"time": round(time.perf_counter() - self._record_start_time, 4),
                  "listener_alive": listener.is_alive(), "event_count": len(self.events)}
        try:
            point = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
            sample["pointer"] = [point.x, point.y]
            sample["left_pressed"] = bool(Quartz.CGEventSourceButtonState(
                Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGMouseButtonLeft))
        except Exception as e:
            sample["pointer_error"] = str(e)
        try:
            from AppKit import NSWorkspace
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            sample["frontmost_app"] = app.bundleIdentifier() if app else None
        except Exception as e:
            sample["frontmost_error"] = str(e)
        return sample

    def stop_recording(self) -> Dict:
        self.state = "IDLE"
        if self.recording_diagnostics:
            self.recording_diagnostics["stopped_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            self.recording_diagnostics["final_permissions"] = self._diagnostic_permissions()
            self.recording_diagnostics["event_count"] = len(self.events)
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

        self.state = "IDLE"
        summary = self.get_summary()
        if self.on_state_change:
            self.on_state_change("IDLE", {"summary": summary})
        return summary

    def toggle_recording(self):
        if self.state == "RECORDING":
            self.stop_recording()
        elif self.state == "IDLE":
            self.start_recording()

    def _on_mouse_move(self, x: float, y: float):
        if self.state != "RECORDING":
            return
        now = time.perf_counter()
        # 不按时间丢点，绘制降频只发生在 UI 层。
        if self._last_pos == (x, y):
            return

        self._last_move_time = now
        self._last_pos = (x, y)
        rel_time = now - self._record_start_time

        evt = {
            "type": "move",
            "time": round(rel_time, 4),
            "x": round(x, 1),
            "y": round(y, 1),
            "count": len(self.events) + 1,
        }
        self.events.append(evt)

        if self.on_event_broadcast:
            self.on_event_broadcast(evt)

    def _on_mouse_click(self, x: float, y: float, button: mouse.Button, pressed: bool, *args):
        if self.state != "RECORDING":
            return
        now = time.perf_counter()
        rel_time = now - self._record_start_time

        btn_str = "left"
        if button == mouse.Button.right:
            btn_str = "right"
        elif button == mouse.Button.middle:
            btn_str = "middle"

        evt = {
            "type": "click_down" if pressed else "click_up",
            "time": round(rel_time, 4),
            "x": round(x, 1),
            "y": round(y, 1),
            "button": btn_str,
            "count": len(self.events) + 1,
        }
        self.events.append(evt)

        if self.on_event_broadcast:
            self.on_event_broadcast(evt)

    def _on_mouse_scroll(self, x: float, y: float, dx: int, dy: int):
        if self.state != "RECORDING":
            return
        now = time.perf_counter()
        rel_time = now - self._record_start_time

        evt = {
            "type": "scroll",
            "time": round(rel_time, 4),
            "x": round(x, 1),
            "y": round(y, 1),
            "dx": dx,
            "dy": dy,
            "count": len(self.events) + 1,
        }
        self.events.append(evt)

        if self.on_event_broadcast:
            self.on_event_broadcast(evt)

    def start_playback(self, config: Optional[Dict] = None) -> Dict:
        # 1. 权限强检测：杜绝因应用重新打包导致系统处于“允许移动光标、但禁止模拟点击”的幽灵失效状态
        from permission_checker import is_accessibility_trusted
        if not is_accessibility_trusted(prompt_user=False):
            if self.on_state_change:
                self.on_state_change("PERMISSION_DENIED", {})
            return {"success": False, "error": "macOS 辅助功能未授权或失效！请根据弹窗指引关闭开关再重新开启。"}

        # 2. 状态自愈：如果线程已经结束但 state 依然停留在非 IDLE，强制自愈为 IDLE
        if self.state in ("COUNTDOWN", "PLAYING") and self._player_thread and not self._player_thread.is_alive():
            self.state = "IDLE"

        # 3. 检查是否有轨迹
        if not self.events:
            err_msg = "当前没有录制任何鼠标轨迹！请先点击【开始录制 (F7)】在屏幕上操作后再回放。"
            if self.on_state_change:
                self.on_state_change("ERROR", {"message": err_msg})
            return {"success": False, "error": err_msg}

        if self.state != "IDLE":
            err_msg = f"当前引擎正处于【{self.state}】状态，请先按 Esc 停止或稍后再试。"
            if self.on_state_change:
                self.on_state_change("ERROR", {"message": err_msg})
            return {"success": False, "error": err_msg}

        if not self._keyboard_listener or not self._keyboard_listener.is_alive():
            self._init_hotkeys()
        config = config or {}
        loop_count = config.get("loop_count", 1)
        speed_factor = max(0.1, float(config.get("speed_factor", 1.0)))
        countdown_sec = max(0, int(config.get("countdown_seconds", 3)))
        loop_interval = max(0.0, float(config.get("loop_interval", 0.5)))

        self._abort_requested = False
        self._corner_hit_count = 0
        self._play_start_time = time.perf_counter()

        self._player_thread = threading.Thread(
            target=self._run_playback_thread,
            args=(loop_count, speed_factor, countdown_sec, loop_interval),
            daemon=True,
        )
        self.state = "COUNTDOWN" if countdown_sec > 0 else "PLAYING"
        self._player_thread.start()
        return {"success": True}

    def stop_playback(self):
        if self.state in ("COUNTDOWN", "PLAYING"):
            self._abort_requested = True

    def toggle_playback(self):
        if self.state in ("COUNTDOWN", "PLAYING"):
            self.stop_playback()
        elif self.state == "IDLE":
            self.start_playback()

    def _sleep_interruptible(self, seconds: float) -> bool:
        """可被按键或鼠标物理甩角打断的高灵敏休眠"""
        end_time = time.perf_counter() + seconds
        while time.perf_counter() < end_time:
            corner_triggered = self._check_corner_failsafe()
            if self._abort_requested or corner_triggered:
                self._abort_requested = True
                return False
            chunk = min(0.01, end_time - time.perf_counter())
            if chunk > 0:
                time.sleep(chunk)
        return not self._abort_requested

    def _check_corner_failsafe(self) -> bool:
        """物理防失控急停：增加防抖，回放前 0.5 秒内防误触，且需连续检测到在屏幕左上极端角落"""
        if self.state != "PLAYING":
            self._corner_hit_count = 0
            return False
        # 播放刚开始 0.5 秒内忽略角落，防止起点就在左上角造成秒退
        if (time.perf_counter() - self._play_start_time) < 0.5:
            return False
        try:
            pos = self.mouse_controller.position
            # 距离屏幕左上角 4 像素以内
            if 0 < pos[0] <= 4 and 0 < pos[1] <= 4:
                self._corner_hit_count += 1
                if self._corner_hit_count >= 6:
                    return True
            else:
                self._corner_hit_count = 0
        except Exception:
            pass
        return False

    def _run_playback_thread(self, loop_count: int, speed_factor: float, countdown_sec: int, loop_interval: float):
        try:
            # 1. 倒计时阶段
            if countdown_sec > 0:
                self.state = "COUNTDOWN"
                for sec in range(countdown_sec, 0, -1):
                    if self._abort_requested:
                        return
                    if self.on_state_change:
                        self.on_state_change("COUNTDOWN", {"seconds": sec})
                    if not self._sleep_interruptible(1.0):
                        return

            self.state = "PLAYING"
            self._play_start_time = time.perf_counter()
            infinite = (loop_count <= 0)
            current_loop = 0

            # 2. 首帧相对时间归零：去除录制开头长时间静止发呆
            first_time = self.events[0]["time"] if self.events else 0.0
            normalized_events = []
            for evt in self.events:
                evt_copy = dict(evt)
                evt_copy["time"] = max(0.0, evt["time"] - first_time)
                normalized_events.append(evt_copy)

            while infinite or (current_loop < loop_count):
                if self._abort_requested:
                    break

                current_loop += 1
                self._last_click_time = 0.0
                self._last_click_button = None
                if self.on_state_change:
                    self.on_state_change("PLAYING", {
                        "current": current_loop,
                        "total": 0 if infinite else loop_count,
                    })

                loop_start = time.perf_counter()

                for evt in normalized_events:
                    if self._abort_requested:
                        break

                    target_rel_time = evt["time"] / speed_factor
                    wait_time = target_rel_time - (time.perf_counter() - loop_start)
                    if wait_time > 0:
                        if not self._sleep_interruptible(wait_time):
                            break

                    self._dispatch_event(evt)

                # 不完整录制也不能把按下状态带入下一轮。
                self._safety_release()
                if self._abort_requested:
                    break

                if (infinite or current_loop < loop_count) and loop_interval > 0:
                    if not self._sleep_interruptible(loop_interval):
                        break

        except Exception as e:
            print(f"回放线程异常: {e}")
            if self.on_state_change:
                self.on_state_change("ERROR", {"message": f"回放过程出现异常: {e}"})
        finally:
            # 释放可能按下的鼠标按键
            self._safety_release()
            self.state = "IDLE"
            if self.on_state_change:
                self.on_state_change("IDLE", {"summary": self.get_summary()})

    def _post_hid_event(self, ev):
        """派发失败必须交给回放线程报告，不能伪装成点击成功。"""
        if ev is None:
            raise RuntimeError("无法创建鼠标事件")
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    def _dispatch_event(self, evt: Dict):
        etype = evt["type"]
        x, y = evt["x"], evt["y"]
        pt = Quartz.CGPointMake(x, y)

        if etype == "move":
            mtype, btn = Quartz.kCGEventMouseMoved, Quartz.kCGMouseButtonLeft
            for name, drag_type, button in [
                ("left", Quartz.kCGEventLeftMouseDragged, Quartz.kCGMouseButtonLeft),
                ("right", Quartz.kCGEventRightMouseDragged, Quartz.kCGMouseButtonRight),
                ("middle", Quartz.kCGEventOtherMouseDragged, Quartz.kCGMouseButtonCenter),
            ]:
                if name in self._pressed_buttons:
                    mtype, btn = drag_type, button
                    break
            ev = Quartz.CGEventCreateMouseEvent(self._event_source, mtype, pt, btn)
            self._post_hid_event(ev)

            # 回放时同步广播至前端雷达画布追踪
            if self.on_event_broadcast:
                self.on_event_broadcast({"type": "move", "x": x, "y": y})

        elif etype in ("click_down", "click_up"):
            btn_str = evt.get("button", "left")
            if etype == "click_up" and btn_str not in self._pressed_buttons:
                return

            if btn_str == "right":
                mtype_down = Quartz.kCGEventRightMouseDown
                mtype_up = Quartz.kCGEventRightMouseUp
                btn = Quartz.kCGMouseButtonRight
            elif btn_str == "middle":
                mtype_down = Quartz.kCGEventOtherMouseDown
                mtype_up = Quartz.kCGEventOtherMouseUp
                btn = Quartz.kCGMouseButtonCenter
            else:
                mtype_down = Quartz.kCGEventLeftMouseDown
                mtype_up = Quartz.kCGEventLeftMouseUp
                btn = Quartz.kCGMouseButtonLeft

            if etype == "click_down":
                now = time.perf_counter()
                dist = abs(x - self._last_click_pos[0]) + abs(y - self._last_click_pos[1])
                if (now - self._last_click_time < 0.45 and dist < 8
                        and getattr(self, "_last_click_button", None) == btn_str):
                    self._click_count += 1
                else:
                    self._click_count = 1
                self._last_click_time = now
                self._last_click_pos = (x, y)
                self._last_click_button = btn_str
                self._button_click_counts[btn_str] = self._click_count
                # 先登记，确保派发异常时也能尝试释放。
                self._pressed_buttons.add(btn_str)

            ev = Quartz.CGEventCreateMouseEvent(
                self._event_source, mtype_down if etype == "click_down" else mtype_up, pt, btn)
            Quartz.CGEventSetIntegerValueField(
                ev, Quartz.kCGMouseEventClickState, self._button_click_counts.get(btn_str, 1))
            self._post_hid_event(ev)
            if etype == "click_up":
                self._pressed_buttons.discard(btn_str)

            # 7. 回放时向界面广播水波纹动画与点击状态
            if self.on_event_broadcast:
                self.on_event_broadcast({"type": etype, "x": x, "y": y, "button": btn_str})

        elif etype == "scroll":
            Quartz.CGWarpMouseCursorPosition(pt)
            dx = evt.get("dx", 0)
            dy = evt.get("dy", 0)
            ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 2, dy * 10, dx * 10)
            self._post_hid_event(ev)

    def _safety_release(self):
        for name, mtype, btn in [
            ("left", Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
            ("right", Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight),
            ("middle", Quartz.kCGEventOtherMouseUp, Quartz.kCGMouseButtonCenter),
        ]:
            if name not in self._pressed_buttons:
                continue
            try:
                pt = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                ev = Quartz.CGEventCreateMouseEvent(self._event_source, mtype, pt, btn)
                Quartz.CGEventSetIntegerValueField(
                    ev, Quartz.kCGMouseEventClickState, self._button_click_counts.get(name, 1))
                self._post_hid_event(ev)
                self._pressed_buttons.discard(name)
            except Exception as e:
                print(f"释放鼠标 {name} 失败: {e}")

    def get_summary(self) -> Dict:
        total = len(self.events)
        dur = self.events[-1]["time"] if total > 0 else 0.0
        clicks = sum(1 for e in self.events if e["type"] == "click_down")
        return {
            "total_events": total,
            "click_count": clicks,
            "duration": round(dur, 2),
        }
