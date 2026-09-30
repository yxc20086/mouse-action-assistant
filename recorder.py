"""
鼠标动作录制模块 (MouseRecorder)
负责全局监听鼠标移动、点击、滚轮操作，并以相对时间戳记录完整的轨迹流。
"""
import json
import time
from typing import Callable, Dict, List, Optional
from pynput import mouse


class MouseRecorder:
    def __init__(self, on_event_recorded: Optional[Callable[[int, float], None]] = None):
        """
        :param on_event_recorded: 每次记录新事件时的回调函数 (参数: 当前事件总数, 录制时长)
        """
        self.on_event_recorded = on_event_recorded
        self.events: List[Dict] = []
        self.is_recording: bool = False
        self.start_time: float = 0.0
        self._listener: Optional[mouse.Listener] = None
        self._last_move_time: float = 0.0
        self._last_x: Optional[float] = None
        self._last_y: Optional[float] = None

    def start(self) -> None:
        """开始录制鼠标轨迹"""
        if self.is_recording:
            return

        self.events = []
        self.is_recording = True
        self.start_time = time.perf_counter()
        self._last_move_time = self.start_time
        self._last_x = None
        self._last_y = None

        # 启动全局鼠标监听器
        self._listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> List[Dict]:
        """停止录制并返回记录的所有事件列表"""
        if not self.is_recording:
            return self.events

        self.is_recording = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

        return self.events

    def _on_move(self, x: float, y: float) -> None:
        if not self.is_recording:
            return

        current_time = time.perf_counter()
        # 降噪与优化：限制移动采样频率（不少于 5ms 间隔）且必须有实际位移
        if (current_time - self._last_move_time < 0.005) or (
            self._last_x == x and self._last_y == y
        ):
            return

        self._last_move_time = current_time
        self._last_x = x
        self._last_y = y

        rel_time = current_time - self.start_time
        self.events.append({
            "type": "move",
            "time": round(rel_time, 4),
            "x": round(x, 1),
            "y": round(y, 1),
        })

        if self.on_event_recorded:
            self.on_event_recorded(len(self.events), rel_time)

    def _on_click(self, x: float, y: float, button: mouse.Button, pressed: bool) -> None:
        if not self.is_recording:
            return

        current_time = time.perf_counter()
        rel_time = current_time - self.start_time

        # 转换按键名称
        button_name = "left"
        if button == mouse.Button.right:
            button_name = "right"
        elif button == mouse.Button.middle:
            button_name = "middle"

        self.events.append({
            "type": "click_down" if pressed else "click_up",
            "time": round(rel_time, 4),
            "x": round(x, 1),
            "y": round(y, 1),
            "button": button_name,
        })

        if self.on_event_recorded:
            self.on_event_recorded(len(self.events), rel_time)

    def _on_scroll(self, x: float, y: float, dx: int, dy: int) -> None:
        if not self.is_recording:
            return

        current_time = time.perf_counter()
        rel_time = current_time - self.start_time

        self.events.append({
            "type": "scroll",
            "time": round(rel_time, 4),
            "x": round(x, 1),
            "y": round(y, 1),
            "dx": dx,
            "dy": dy,
        })

        if self.on_event_recorded:
            self.on_event_recorded(len(self.events), rel_time)

    def get_summary(self) -> Dict:
        """获取当前录制轨迹的统计信息"""
        total_events = len(self.events)
        total_duration = self.events[-1]["time"] if total_events > 0 else 0.0
        click_count = sum(1 for e in self.events if e["type"] == "click_down")
        return {
            "total_events": total_events,
            "duration": round(total_duration, 2),
            "click_count": click_count,
        }

    def save_to_file(self, filepath: str) -> None:
        """保存轨迹为 JSON 文件"""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.events, f, indent=2, ensure_ascii=False)

    def load_from_file(self, filepath: str) -> List[Dict]:
        """从 JSON 文件载入轨迹"""
        with open(filepath, "r", encoding="utf-8") as f:
            self.events = json.load(f)
        return self.events
