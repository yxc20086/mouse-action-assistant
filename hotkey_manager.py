"""
全局快捷键与急停监控模块 (HotkeyManager)
通过 pynput.keyboard.Listener 实现系统全局级别的按键拦截。
支持 Esc 紧急强行停止、F7 录制切换、F8 回放切换。
"""
from typing import Callable, Optional
from pynput import keyboard


class HotkeyManager:
    def __init__(
        self,
        on_toggle_record: Optional[Callable[[], None]] = None,
        on_toggle_play: Optional[Callable[[], None]] = None,
        on_emergency_stop: Optional[Callable[[], None]] = None,
    ):
        self.on_toggle_record = on_toggle_record
        self.on_toggle_play = on_toggle_play
        self.on_emergency_stop = on_emergency_stop
        self._listener: Optional[keyboard.Listener] = None
        self._ctrl_pressed = False

    def start(self) -> None:
        """启动后台键盘监听"""
        if self._listener is not None:
            return

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """停止监听"""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        try:
            # 记录 Ctrl 状态以支持 Ctrl+R / Ctrl+P 快捷键
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self._ctrl_pressed = True

            # 1. 紧急停止：按下 Esc 键
            if key == keyboard.Key.esc:
                if self.on_emergency_stop:
                    self.on_emergency_stop()
                return

            # 2. 录制切换：F7 或 Ctrl+R
            if key == keyboard.Key.f7 or (
                self._ctrl_pressed and hasattr(key, 'char') and key.char in ('r', 'R')
            ):
                if self.on_toggle_record:
                    self.on_toggle_record()
                return

            # 3. 回放切换：F8 或 Ctrl+P
            if key == keyboard.Key.f8 or (
                self._ctrl_pressed and hasattr(key, 'char') and key.char in ('p', 'P')
            ):
                if self.on_toggle_play:
                    self.on_toggle_play()
                return

        except Exception:
            pass

    def _on_release(self, key) -> None:
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._ctrl_pressed = False
