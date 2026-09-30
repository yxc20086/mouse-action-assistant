"""
鼠标动作回放引擎模块 (MousePlayer)
负责高精度回放录制好的轨迹，支持多轮循环、调速、循环间隔、倒计时启动以及随时紧急强行中断。
"""
import threading
import time
from typing import Callable, Dict, List, Optional
from pynput import mouse


class MousePlayer:
    def __init__(
        self,
        on_status_change: Optional[Callable[[str, int, int], None]] = None,
        on_countdown: Optional[Callable[[int], None]] = None,
        on_finished: Optional[Callable[[bool], None]] = None,
    ):
        """
        :param on_status_change: 状态变化回调 (状态描述, 当前循环轮次, 总循环轮次)
        :param on_countdown: 启动倒计时回调 (剩余秒数)
        :param on_finished: 回放结束回调 (是否被提前中断)
        """
        self.on_status_change = on_status_change
        self.on_countdown = on_countdown
        self.on_finished = on_finished

        self.controller = mouse.Controller()
        self.is_playing: bool = False
        self._abort_requested: bool = False
        self._worker_thread: Optional[threading.Thread] = None

    def start_playback(
        self,
        events: List[Dict],
        loop_count: int = 1,
        speed_factor: float = 1.0,
        loop_interval: float = 0.5,
        countdown_seconds: int = 3,
    ) -> None:
        """在后台守护线程中启动回放流程"""
        if self.is_playing or not events:
            return

        self.is_playing = True
        self._abort_requested = False

        self._worker_thread = threading.Thread(
            target=self._run_playback,
            args=(events, loop_count, speed_factor, loop_interval, countdown_seconds),
            daemon=True,
        )
        self._worker_thread.start()

    def abort(self) -> None:
        """紧急终止回放"""
        if not self.is_playing:
            return
        self._abort_requested = True

    def _sleep_interruptible(self, seconds: float) -> bool:
        """
        可被即时打断的精准休眠函数。
        返回 True 表示正常休眠完成，返回 False 表示收到了中断请求。
        """
        end_time = time.perf_counter() + seconds
        while time.perf_counter() < end_time:
            if self._abort_requested:
                return False
            # 采用 10ms 步进轮询，保证紧急停止按键响应延迟不超过 0.01 秒
            sleep_chunk = min(0.01, end_time - time.perf_counter())
            if sleep_chunk > 0:
                time.sleep(sleep_chunk)
        return not self._abort_requested

    def _run_playback(
        self,
        events: List[Dict],
        loop_count: int,
        speed_factor: float,
        loop_interval: float,
        countdown_seconds: int,
    ) -> None:
        aborted = False

        try:
            # 1. 启动倒计时，给用户准备切换目标窗口的时间
            for remaining in range(countdown_seconds, 0, -1):
                if self._abort_requested:
                    aborted = True
                    return
                if self.on_countdown:
                    self.on_countdown(remaining)
                if not self._sleep_interruptible(1.0):
                    aborted = True
                    return

            if self.on_countdown:
                self.on_countdown(0)

            # 2. 循环执行回放
            current_loop = 0
            infinite = loop_count <= 0

            while infinite or (current_loop < loop_count):
                if self._abort_requested:
                    aborted = True
                    break

                current_loop += 1
                if self.on_status_change:
                    total_display = 0 if infinite else loop_count
                    self.on_status_change("playing", current_loop, total_display)

                loop_start_time = time.perf_counter()

                for event in events:
                    if self._abort_requested:
                        aborted = True
                        break

                    # 计算经过加速/减速后的目标执行时间点
                    target_rel_time = event["time"] / speed_factor
                    time_to_wait = target_rel_time - (time.perf_counter() - loop_start_time)
                    if time_to_wait > 0:
                        if not self._sleep_interruptible(time_to_wait):
                            aborted = True
                            break

                    # 执行具体的鼠标动作
                    self._dispatch_event(event)

                if aborted:
                    break

                # 单次循环结束后的间隔停顿
                if (infinite or current_loop < loop_count) and loop_interval > 0:
                    if not self._sleep_interruptible(loop_interval):
                        aborted = True
                        break

        finally:
            # 安全保护：释放可能处于按下状态的鼠标按键，避免造成鼠标“卡键”
            self._safety_release_buttons()
            self.is_playing = False
            if self.on_finished:
                self.on_finished(aborted)

    def _dispatch_event(self, event: Dict) -> None:
        """分发执行单条鼠标指令"""
        etype = event["type"]
        x = event["x"]
        y = event["y"]

        if etype == "move":
            self.controller.position = (x, y)
        elif etype in ("click_down", "click_up"):
            btn_str = event.get("button", "left")
            btn = mouse.Button.left
            if btn_str == "right":
                btn = mouse.Button.right
            elif btn_str == "middle":
                btn = mouse.Button.middle

            self.controller.position = (x, y)
            if etype == "click_down":
                self.controller.press(btn)
            else:
                self.controller.release(btn)
        elif etype == "scroll":
            self.controller.position = (x, y)
            self.controller.scroll(event.get("dx", 0), event.get("dy", 0))

    def _safety_release_buttons(self) -> None:
        """安全保险：强制松开所有常用鼠标按键"""
        try:
            self.controller.release(mouse.Button.left)
            self.controller.release(mouse.Button.right)
            self.controller.release(mouse.Button.middle)
        except Exception:
            pass
