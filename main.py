"""
macOS 鼠标动作录制与循环回放工具 - 主 GUI 程序
"""
import os
import sys

os.environ["TK_SILENCE_DEPRECATION"] = "1"

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List

from hotkey_manager import HotkeyManager
from permission_checker import is_accessibility_trusted, open_accessibility_settings
from player import MousePlayer
from recorder import MouseRecorder


class MouseMacroApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("macOS 鼠标路径录制与循环播放器")
        self.root.geometry("640x720")
        self.root.minsize(580, 680)

        # 核心逻辑模块
        self.recorder = MouseRecorder(on_event_recorded=self._on_event_recorded_threadsafe)
        self.player = MousePlayer(
            on_status_change=self._on_play_status_threadsafe,
            on_countdown=self._on_countdown_threadsafe,
            on_finished=self._on_play_finished_threadsafe,
        )
        self.hotkey_mgr = HotkeyManager(
            on_toggle_record=self._hotkey_toggle_record,
            on_toggle_play=self._hotkey_toggle_play,
            on_emergency_stop=self._hotkey_emergency_stop,
        )

        # 内部状态
        self.current_events: List[Dict] = []
        self.is_recording = False
        self.is_playing = False

        # 初始化现代视觉样式与 UI 界面
        self._setup_style()
        self._build_ui()

        # 启动全局快捷键监听
        self.hotkey_mgr.start()

        # 检查辅助功能权限
        self.root.after(500, self._check_permission)

        # 绑定退出事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        """配置简洁现代的 macOS 配色风格"""
        self.root.configure(bg="#F2F3F7")

        self.style = ttk.Style()
        self.style.theme_use("clam")

        # 统一字体
        self.default_font = ("SF Pro Text", 12)
        self.title_font = ("SF Pro Display", 15, "bold")
        self.large_font = ("SF Pro Display", 18, "bold")
        self.small_font = ("SF Pro Text", 10)

        # 样式定义
        self.style.configure(".", background="#F2F3F7", font=self.default_font, foreground="#1C1C1E")
        self.style.configure("Card.TFrame", background="#FFFFFF", relief="flat")
        self.style.configure("CardTitle.TLabel", background="#FFFFFF", font=self.title_font, foreground="#1C1C1E")
        self.style.configure("SubText.TLabel", background="#FFFFFF", font=self.small_font, foreground="#8E8E93")

    def _build_ui(self):
        """构建应用主界面"""
        main_container = ttk.Frame(self.root, padding=16)
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. 权限提醒栏 (初始隐藏)
        self.perm_frame = tk.Frame(main_container, bg="#FFF3CD", relief="solid", bd=1)
        perm_label = tk.Label(
            self.perm_frame,
            text="⚠️ 提示：macOS 需要【辅助功能】权限以录制与模拟鼠标事件。",
            bg="#FFF3CD",
            fg="#856404",
            font=self.default_font,
        )
        perm_label.pack(side=tk.LEFT, padx=12, pady=8)
        perm_btn = tk.Button(
            self.perm_frame,
            text="一键打开设置",
            command=open_accessibility_settings,
            bg="#FFEBAA",
            fg="#856404",
            relief="groove",
            font=self.small_font,
            cursor="pointinghand",
        )
        perm_btn.pack(side=tk.RIGHT, padx=12, pady=6)

        # 2. 状态显示横幅 (Card 1)
        status_card = ttk.Frame(main_container, style="Card.TFrame", padding=16)
        status_card.pack(fill=tk.X, pady=(0, 12))

        self.status_title = ttk.Label(status_card, text="⚪ 空闲就绪", font=self.large_font, style="CardTitle.TLabel")
        self.status_title.pack(anchor="w")

        self.status_detail = ttk.Label(
            status_card,
            text="尚未开始录制或回放。可点击下方按钮或使用快捷键操作。",
            style="SubText.TLabel",
        )
        self.status_detail.pack(anchor="w", pady=(4, 0))

        # 3. 核心控制按钮栏 (Card 2)
        action_card = ttk.Frame(main_container, style="Card.TFrame", padding=16)
        action_card.pack(fill=tk.X, pady=(0, 12))

        btn_row = ttk.Frame(action_card, style="Card.TFrame")
        btn_row.pack(fill=tk.X)

        self.record_btn = tk.Button(
            btn_row,
            text="🔴 开始录制 (F7 / Ctrl+R)",
            command=self.toggle_record,
            font=("SF Pro Text", 13, "bold"),
            bg="#FF3B30",
            fg="#FFFFFF",
            activebackground="#D32F2F",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=16,
            pady=10,
            cursor="pointinghand",
        )
        self.record_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 8))

        self.play_btn = tk.Button(
            btn_row,
            text="▶ 开始回放 (F8 / Ctrl+P)",
            command=self.toggle_play,
            font=("SF Pro Text", 13, "bold"),
            bg="#007AFF",
            fg="#FFFFFF",
            activebackground="#005ECB",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=16,
            pady=10,
            cursor="pointinghand",
        )
        self.play_btn.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(8, 0))

        # 4. 回放参数配置区 (Card 3)
        config_card = ttk.Frame(main_container, style="Card.TFrame", padding=16)
        config_card.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(config_card, text="⚙️ 回放参数配置", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))

        # 循环次数
        loop_row = ttk.Frame(config_card, style="Card.TFrame")
        loop_row.pack(fill=tk.X, pady=4)
        ttk.Label(loop_row, text="循环播放次数：", style="Card.TLabel").pack(side=tk.LEFT)

        self.loop_count_var = tk.StringVar(value="1")
        self.loop_entry = ttk.Entry(loop_row, textvariable=self.loop_count_var, width=8)
        self.loop_entry.pack(side=tk.LEFT, padx=6)

        self.infinite_var = tk.BooleanVar(value=False)
        self.infinite_check = ttk.Checkbutton(
            loop_row,
            text="无限循环 (按 Esc 键停止)",
            variable=self.infinite_var,
            command=self._on_infinite_toggle,
        )
        self.infinite_check.pack(side=tk.LEFT, padx=12)

        # 回放倍速
        speed_row = ttk.Frame(config_card, style="Card.TFrame")
        speed_row.pack(fill=tk.X, pady=4)
        ttk.Label(speed_row, text="回放倍速：", style="Card.TLabel").pack(side=tk.LEFT)

        self.speed_var = tk.StringVar(value="1.0x (原速)")
        speed_options = ["0.5x (半速)", "1.0x (原速)", "1.5x (快速)", "2.0x (两倍速)", "3.0x (极速)", "5.0x (光速)"]
        self.speed_combo = ttk.Combobox(
            speed_row,
            textvariable=self.speed_var,
            values=speed_options,
            state="readonly",
            width=14,
        )
        self.speed_combo.pack(side=tk.LEFT, padx=6)

        # 启动前倒计时与单次循环间隔
        delay_row = ttk.Frame(config_card, style="Card.TFrame")
        delay_row.pack(fill=tk.X, pady=4)

        ttk.Label(delay_row, text="启动前倒计时：", style="Card.TLabel").pack(side=tk.LEFT)
        self.countdown_var = tk.StringVar(value="3")
        self.countdown_entry = ttk.Entry(delay_row, textvariable=self.countdown_var, width=5)
        self.countdown_entry.pack(side=tk.LEFT, padx=4)
        ttk.Label(delay_row, text="秒 (方便切换窗口)", style="SubText.TLabel").pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(delay_row, text="每轮间隔：", style="Card.TLabel").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="0.5")
        self.interval_entry = ttk.Entry(delay_row, textvariable=self.interval_var, width=5)
        self.interval_entry.pack(side=tk.LEFT, padx=4)
        ttk.Label(delay_row, text="秒", style="SubText.TLabel").pack(side=tk.LEFT)

        # 5. 轨迹文件与数据管理 (Card 4)
        track_card = ttk.Frame(main_container, style="Card.TFrame", padding=16)
        track_card.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(track_card, text="📁 轨迹数据与文件", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        self.track_summary_label = ttk.Label(
            track_card,
            text="当前轨迹：无记录",
            style="Card.TLabel",
            foreground="#007AFF",
        )
        self.track_summary_label.pack(anchor="w", pady=(0, 8))

        file_btn_row = ttk.Frame(track_card, style="Card.TFrame")
        file_btn_row.pack(fill=tk.X)

        self.save_btn = ttk.Button(file_btn_row, text="💾 保存轨迹到文件", command=self.save_track)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.load_btn = ttk.Button(file_btn_row, text="📂 从文件加载轨迹", command=self.load_track)
        self.load_btn.pack(side=tk.LEFT, padx=6)

        self.clear_btn = ttk.Button(file_btn_row, text="🗑 清空", command=self.clear_track)
        self.clear_btn.pack(side=tk.LEFT, padx=6)

        # 6. 底部快捷键指南栏
        tips_frame = ttk.Frame(main_container, padding=8)
        tips_frame.pack(fill=tk.X, side=tk.BOTTOM)

        tips_text = (
            "💡 全局快捷键指南：\n"
            "• Esc 键：任何时候紧急终止回放！\n"
            "• F7 或 Ctrl+R：开始 / 停止录制\n"
            "• F8 或 Ctrl+P：开始 / 停止回放\n"
            "• 回放时全局光标受控，如需临时使用鼠标，请直接按 Esc 停止即可恢复自由。"
        )
        tips_label = ttk.Label(
            tips_frame,
            text=tips_text,
            font=self.small_font,
            foreground="#636366",
            justify=tk.LEFT,
        )
        tips_label.pack(anchor="w")

    def _check_permission(self):
        """检查辅助功能权限状态并在界面上展示引导"""
        trusted = is_accessibility_trusted(prompt_user=False)
        if not trusted:
            self.perm_frame.pack(fill=tk.X, pady=(0, 10), before=self.perm_frame.master.winfo_children()[1])
        else:
            self.perm_frame.pack_forget()

    def _on_infinite_toggle(self):
        """切换无限循环状态"""
        if self.infinite_var.get():
            self.loop_entry.configure(state="disabled")
        else:
            self.loop_entry.configure(state="normal")

    def toggle_record(self):
        """开始 / 停止录制"""
        if self.is_playing:
            messagebox.showwarning("提示", "正在回放中，无法录制。请先等待或按 Esc 停止回放。")
            return

        if not self.is_recording:
            # 开始录制
            self.is_recording = True
            self.status_title.configure(text="🔴 正在录制鼠标轨迹...", foreground="#FF3B30")
            self.status_detail.configure(text="已录制: 0 个动作 | 时长: 0.0 秒 (按 F7 或 Ctrl+R 停止)")
            self.record_btn.configure(
                text="⏹ 停止录制 (F7 / Ctrl+R)",
                bg="#8E8E93",
                activebackground="#636366",
            )
            self.play_btn.configure(state="disabled")
            self.recorder.start()
        else:
            # 停止录制
            self.is_recording = False
            self.current_events = self.recorder.stop()
            self.record_btn.configure(
                text="🔴 开始录制 (F7 / Ctrl+R)",
                bg="#FF3B30",
                activebackground="#D32F2F",
            )
            self.play_btn.configure(state="normal")
            summary = self.recorder.get_summary()
            self.status_title.configure(text="⚪ 录制完成", foreground="#1C1C1E")
            self.status_detail.configure(
                text=f"录制完成！共包含 {summary['total_events']} 个动作，{summary['click_count']} 次点击，总时长 {summary['duration']} 秒。"
            )
            self._update_track_summary()

    def toggle_play(self):
        """开始 / 停止回放"""
        if self.is_recording:
            messagebox.showwarning("提示", "正在录制中，请先停止录制。")
            return

        if not self.is_playing:
            if not self.current_events:
                messagebox.showwarning("提示", "当前没有可回放的鼠标轨迹！请先录制或载入文件。")
                return

            # 解析配置参数
            try:
                if self.infinite_var.get():
                    loop_count = 0
                else:
                    loop_count = int(self.loop_count_var.get().strip())
                    if loop_count <= 0:
                        raise ValueError
            except ValueError:
                messagebox.showerror("参数错误", "请输入有效的正整数循环次数！")
                return

            # 解析倍速
            speed_map = {
                "0.5x (半速)": 0.5,
                "1.0x (原速)": 1.0,
                "1.5x (快速)": 1.5,
                "2.0x (两倍速)": 2.0,
                "3.0x (极速)": 3.0,
                "5.0x (光速)": 5.0,
            }
            speed_factor = speed_map.get(self.speed_var.get(), 1.0)

            # 解析倒计时与间隔
            try:
                countdown = max(0, int(self.countdown_var.get().strip()))
                interval = max(0.0, float(self.interval_var.get().strip()))
            except ValueError:
                messagebox.showerror("参数错误", "倒计时与间隔时间必须为有效数字！")
                return

            self.is_playing = True
            self.play_btn.configure(
                text="🛑 紧急停止 (Esc)",
                bg="#FF3B30",
                activebackground="#D32F2F",
            )
            self.record_btn.configure(state="disabled")

            # 启动播放引擎
            self.player.start_playback(
                events=self.current_events,
                loop_count=loop_count,
                speed_factor=speed_factor,
                loop_interval=interval,
                countdown_seconds=countdown,
            )
        else:
            # 停止回放
            self.player.abort()

    def save_track(self):
        """保存当前轨迹到 JSON 文件"""
        if not self.current_events:
            messagebox.showinfo("提示", "当前无轨迹数据可保存。")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON 轨迹文件", "*.json")],
            initialdir=os.path.dirname(os.path.abspath(__file__)),
            initialfile="mouse_track.json",
        )
        if filepath:
            try:
                self.recorder.events = self.current_events
                self.recorder.save_to_file(filepath)
                messagebox.showinfo("成功", f"轨迹已成功保存至:\n{os.path.basename(filepath)}")
            except Exception as e:
                messagebox.showerror("保存失败", str(e))

    def load_track(self):
        """从文件加载轨迹"""
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON 轨迹文件", "*.json")],
            initialdir=os.path.dirname(os.path.abspath(__file__)),
        )
        if filepath:
            try:
                self.current_events = self.recorder.load_from_file(filepath)
                self._update_track_summary()
                summary = self.recorder.get_summary()
                self.status_title.configure(text="⚪ 轨迹已载入", foreground="#1C1C1E")
                self.status_detail.configure(
                    text=f"成功载入文件 {os.path.basename(filepath)}（共 {summary['total_events']} 个动作，{summary['click_count']} 次点击）。"
                )
            except Exception as e:
                messagebox.showerror("加载失败", f"文件格式不正确或无法读取: {e}")

    def clear_track(self):
        """清空当前轨迹"""
        if self.is_recording or self.is_playing:
            return
        self.current_events = []
        self._update_track_summary()
        self.status_title.configure(text="⚪ 空闲就绪", foreground="#1C1C1E")
        self.status_detail.configure(text="轨迹已清空。")

    def _update_track_summary(self):
        """刷新当前轨迹数据概要"""
        if not self.current_events:
            self.track_summary_label.configure(text="当前轨迹：无记录", foreground="#8E8E93")
        else:
            self.recorder.events = self.current_events
            summary = self.recorder.get_summary()
            self.track_summary_label.configure(
                text=f"当前轨迹：{summary['total_events']} 个动作 | {summary['click_count']} 次点击 | 时长: {summary['duration']} 秒",
                foreground="#007AFF",
            )

    # ---------------- 线程安全的回调通知 ----------------
    def _on_event_recorded_threadsafe(self, count: int, duration: float):
        self.root.after(0, self._update_record_status, count, duration)

    def _update_record_status(self, count: int, duration: float):
        if self.is_recording:
            self.status_detail.configure(
                text=f"已录制: {count} 个动作 | 持续: {duration:.1f} 秒 (按 F7 或 Ctrl+R 停止)"
            )

    def _on_countdown_threadsafe(self, remaining: int):
        self.root.after(0, self._update_countdown_status, remaining)

    def _update_countdown_status(self, remaining: int):
        if remaining > 0:
            self.status_title.configure(text=f"🟡 准备回放... 倒计时 {remaining} 秒", foreground="#FF9500")
            self.status_detail.configure(text="请将鼠标移动或切换到目标窗口界面，即将接管光标...")
        else:
            self.status_title.configure(text="🟢 正在回放鼠标动作...", foreground="#34C759")

    def _on_play_status_threadsafe(self, status: str, current_loop: int, total_loops: int):
        self.root.after(0, self._update_play_status, current_loop, total_loops)

    def _update_play_status(self, current_loop: int, total_loops: int):
        total_str = "无限循环" if total_loops <= 0 else f"{total_loops} 次"
        self.status_title.configure(text=f"🟢 正在回放... [第 {current_loop} / {total_str}]", foreground="#34C759")
        self.status_detail.configure(text="全局光标模拟中。任何时候按下键盘 Esc 键可立即强行中断回放！")

    def _on_play_finished_threadsafe(self, aborted: bool):
        self.root.after(0, self._handle_play_finished, aborted)

    def _handle_play_finished(self, aborted: bool):
        self.is_playing = False
        self.play_btn.configure(
            text="▶ 开始回放 (F8 / Ctrl+P)",
            bg="#007AFF",
            activebackground="#005ECB",
        )
        self.record_btn.configure(state="normal")

        if aborted:
            self.status_title.configure(text="🛑 回放已强行终止", foreground="#FF3B30")
            self.status_detail.configure(text="已通过紧急按键终止回放，鼠标已完全恢复用户控制。")
        else:
            self.status_title.configure(text="⚪ 回放已顺利完成", foreground="#34C759")
            self.status_detail.configure(text="设定的循环次数已全部执行完毕，鼠标已恢复正常使用。")

    # ---------------- 快捷键响应 ----------------
    def _hotkey_toggle_record(self):
        self.root.after(0, self.toggle_record)

    def _hotkey_toggle_play(self):
        self.root.after(0, self.toggle_play)

    def _hotkey_emergency_stop(self):
        self.root.after(0, self._trigger_abort)

    def _trigger_abort(self):
        if self.is_playing:
            self.player.abort()

    def _on_close(self):
        """窗口关闭时安全释放所有监听和线程"""
        if self.is_playing:
            self.player.abort()
        if self.is_recording:
            self.recorder.stop()
        self.hotkey_mgr.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = MouseMacroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
