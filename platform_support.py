"""平台选择与用户数据目录；可在导入 GUI/鼠标库之前使用。"""
import os
from pathlib import Path
import sys


def platform_name():
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "unsupported")


def recordings_directory():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData/Local"))
        return base / "MouseActionAssistant/recordings"
    return Path.home() / "Library/Application Support/com.mouse.macro.assistant/recordings"


def configure_dpi():
    if sys.platform != "win32":
        return
    # 保证监听坐标、SendInput 坐标和 GUI 使用同一物理坐标系。
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        function = user32.SetProcessDpiAwarenessContext
        function.argtypes = [ctypes.c_void_p]
        function.restype = ctypes.c_int
        function(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2；清单已设置时可以返回拒绝访问。
    except AttributeError:
        user32.SetProcessDPIAware()
