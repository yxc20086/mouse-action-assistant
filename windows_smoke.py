"""仅在专用 Windows CI 桌面运行的真实输入/GUI 冒烟测试。"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback


def run(output):
    if sys.platform != "win32" or os.environ.get("MOUSE_ASSISTANT_CI_SMOKE") != "1":
        raise RuntimeError("Windows smoke test requires an explicitly enabled CI desktop")
    from platform_support import configure_dpi
    configure_dpi()
    import webview
    from api import JsBridgeAPI
    from app import get_ui_content
    from pynput import keyboard
    from windows_mouse import POINT

    output = Path(output).resolve()
    report = {"passed": False, "platform": sys.platform, "frozen": bool(getattr(sys, "frozen", False))}
    with tempfile.TemporaryDirectory() as directory:
        api = JsBridgeAPI(Path(directory)/"records")
        window = webview.create_window("Mouse Assistant CI " + str(os.getpid()), html=get_ui_content(), js_api=api,
                                       width=740, height=760, min_size=(680, 680))
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINT)]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.IsIconic.argtypes = [ctypes.c_void_p]
        user32.IsIconic.restype = ctypes.c_int
        user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        user32.GetDpiForWindow.restype = ctypes.c_uint

        def wait_for(predicate, timeout=10):
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(0.05)
            raise AssertionError("Timed out waiting for native test condition")

        def exercise():
            engine = api.engine
            try:
                assert window.events.loaded.wait(20), "WebView2 did not load"
                wait_for(lambda: window.evaluate_js("typeof window.pywebview !== 'undefined' && !!window.pywebview.api"))
                wait_for(lambda: window.evaluate_js("document.getElementById('permText').textContent.includes('Windows')"))
                report["webview2"] = True
                window.evaluate_js("""
                  window.ciInput = {down:0, up:0, move:0, wheel:0};
                  const box = document.createElement('div');
                  box.id = 'ci-input-target'; box.textContent = 'Windows native input test';
                  box.style = 'position:fixed;left:40px;top:90px;width:260px;height:180px;z-index:9999;background:#eef;color:#111;';
                  document.body.appendChild(box);
                  for (const [event,key] of [['mousedown','down'],['mouseup','up'],['mousemove','move'],['wheel','wheel']])
                    box.addEventListener(event, e => {ciInput[key]++; e.preventDefault(); e.stopPropagation();}, {passive:false});
                  box.addEventListener('contextmenu', e => e.preventDefault());
                """)
                hwnd = user32.FindWindowW(None, "Mouse Assistant CI " + str(os.getpid()))
                assert hwnd, "Test window handle not found"
                layout = window.evaluate_js("({height:innerHeight, settingsBottom:document.querySelector('.settings-grid').getBoundingClientRect().bottom, listHeight:document.getElementById('recordList').clientHeight})")
                assert layout["settingsBottom"] <= layout["height"] and layout["listHeight"] > 60, layout
                report["layout"] = layout
                window.minimize()
                wait_for(lambda: bool(user32.IsIconic(hwnd)), 5)
                window.restore()
                wait_for(lambda: not user32.IsIconic(hwnd), 5)
                report["minimize_restore"] = True
                user32.SetForegroundWindow(hwnd)
                origin = POINT()
                assert user32.ClientToScreen(hwnd, ctypes.byref(origin))
                dpr = float(window.evaluate_js("window.devicePixelRatio"))
                x, y = origin.x+round(120*dpr), origin.y+round(170*dpr)
                report["dpi"] = user32.GetDpiForWindow(hwnd)
                report["device_pixel_ratio"] = dpr
                backend = engine.backend
                start = api.start_recording()
                assert start.get("success"), start
                engine._mouse_listener.wait()
                backend.move(x, y, set()); time.sleep(0.08)
                assert abs(backend.position()[0]-x) <= 1 and abs(backend.position()[1]-y) <= 1
                for button in ("left", "right", "middle"):
                    backend.button(x, y, button, True); time.sleep(0.08)
                    backend.button(x, y, button, False); time.sleep(0.08)
                backend.button(x, y, "left", True); time.sleep(0.05)
                backend.move(x+30, y+20, {"left"}); time.sleep(0.05)
                backend.button(x+30, y+20, "left", False); time.sleep(0.08)
                backend.scroll(x, y, 1, -1); time.sleep(0.2)
                api.stop_recording()
                events = list(engine.events)
                assert sum(e["type"] == "click_down" for e in events) == 4, events
                assert sum(e["type"] == "click_up" for e in events) == 4, events
                assert any(e["type"] == "scroll" for e in events), events
                counters = window.evaluate_js("window.ciInput")
                assert counters["down"] == 4 and counters["up"] == 4, counters
                before_play = dict(counters)
                started = api.start_playback({"record_id": api.selected_record_id, "loop_count": 2,
                                             "speed_factor": 1, "countdown_seconds": 0,
                                             "loop_interval": 0.1, "auto_minimize": False})
                assert started.get("success"), started
                wait_for(lambda: engine.state == "IDLE", 15)
                counters = window.evaluate_js("window.ciInput")
                assert counters["down"]-before_play["down"] == 8, counters
                assert counters["up"]-before_play["up"] == 8, counters
                report["native_recorded_events"] = len(events)
                report["native_replay_clicks"] = 8
                engine.events = [dict(type="click_down", x=x, y=y, time=0, button="left"),
                                 dict(type="click_up", x=x, y=y, time=5, button="left")]
                engine.start_playback({"countdown_seconds": 0})
                wait_for(lambda: "left" in engine._pressed_buttons)
                keys = keyboard.Controller(); keys.press(keyboard.Key.esc); keys.release(keyboard.Key.esc)
                wait_for(lambda: engine.state == "IDLE", 5)
                assert not engine._pressed_buttons and not (user32.GetAsyncKeyState(1) & 0x8000)
                report["escape_releases_mouse"] = True
                record_id = api.selected_record_id
                assert api.rename_record(record_id, "Windows 测试记录")["success"]
                from record_store import RecordStore
                assert RecordStore(Path(directory)/"records").get(record_id)["name"] == "Windows 测试记录"
                assert api.delete_record(record_id)["success"]
                assert not api.get_records()["records"]
                report["record_management"] = True
                if getattr(sys, "frozen", False):
                    from app_restart import launch_after_exit
                    marker = Path(directory)/"restart-probe.txt"
                    parent = subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", "Start-Sleep -Seconds 10"],
                                              creationflags=subprocess.CREATE_NO_WINDOW)
                    helper = launch_after_exit([sys.executable, "--ci-probe", str(marker)], parent.pid)
                    try:
                        time.sleep(0.3); assert not marker.exists()
                        parent.terminate(); parent.wait(timeout=5)
                        assert helper.wait(timeout=10) == 0
                        wait_for(marker.exists, 10)
                        assert marker.read_text() == "started"
                        report["frozen_restart_helper"] = True
                    finally:
                        for process in (parent, helper):
                            if process.poll() is None:
                                process.terminate(); process.wait(timeout=5)
                report["passed"] = True
            except Exception:
                report["error"] = traceback.format_exc()
            finally:
                engine.stop_playback()
                if engine.state == "RECORDING":
                    engine.stop_recording()
                engine._safety_release()
                for listener in (engine._mouse_listener, engine._keyboard_listener):
                    if listener:
                        listener.stop()
                try:
                    from PIL import ImageGrab
                    ImageGrab.grab().save(output.with_suffix(".png"))
                except Exception:
                    pass
                output.write_text(json.dumps(report, indent=2), encoding="utf-8")
                window.destroy()

        webview.start(exercise, gui="edgechromium", debug=False)
    return 0 if report["passed"] else 1
