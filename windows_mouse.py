"""Win32 SendInput 后端，使用物理像素和虚拟桌面坐标，支持负坐标副屏。"""
import ctypes

DWORD, LONG, WORD = ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint16
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", DWORD), ("union", INPUTUNION)]


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class WindowsMouseBackend:
    MOVE = 0x0001
    ABSOLUTE = 0x8000
    VIRTUALDESK = 0x4000
    WHEEL = 0x0800
    HWHEEL = 0x1000
    BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}

    def __init__(self, user32=None):
        self.user32 = user32 if user32 is not None else ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = ctypes.c_uint
        self.user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        self.user32.GetCursorPos.restype = ctypes.c_int
        self.user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        self.user32.GetSystemMetrics.restype = ctypes.c_int
        self.user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.user32.GetAsyncKeyState.restype = ctypes.c_short
        self.user32.GetForegroundWindow.restype = ctypes.c_void_p
        self.user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(DWORD)]

    def screen_bounds(self):
        values = [int(self.user32.GetSystemMetrics(i)) for i in (76, 77, 78, 79)]
        if values[2] <= 0 or values[3] <= 0:
            raise RuntimeError("无法读取 Windows 虚拟桌面范围")
        return dict(zip(("x", "y", "width", "height"), values))

    def position(self):
        point = POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            raise RuntimeError("无法读取鼠标位置，当前桌面可能不可访问")
        return point.x, point.y

    def normalize(self, x, y):
        b = self.screen_bounds()
        # SendInput 将 0..65535 映射到虚拟桌面；使用像素中心避免边界取整偏差。
        if not (b["x"] <= x < b["x"]+b["width"] and b["y"] <= y < b["y"]+b["height"]):
            raise ValueError("录制坐标不在当前屏幕范围内，请恢复显示器布局或重新录制")
        return (min(65535, int((round(x)-b["x"]+0.5)*65536/b["width"])),
                min(65535, int((round(y)-b["y"]+0.5)*65536/b["height"])))

    def _send(self, flags, x=0, y=0, data=0):
        event = INPUT(type=0, mi=MOUSEINPUT(x, y, int(data) & 0xffffffff, flags, 0, 0))
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise RuntimeError("Windows 未接受模拟鼠标事件。目标可能以管理员权限运行，或当前处于锁屏/UAC 安全桌面；请使用相同权限级别")

    def move(self, x, y, pressed):
        nx, ny = self.normalize(x, y)
        self._send(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK, nx, ny)

    def button(self, x, y, name, pressed, click_count=1):
        nx, ny = self.normalize(x, y)
        flag = self.BUTTONS[name][0 if pressed else 1]
        self._send(self.MOVE | self.ABSOLUTE | self.VIRTUALDESK | flag, nx, ny)

    def scroll(self, x, y, dx, dy):
        self.move(x, y, set())
        if dy:
            self._send(self.WHEEL, data=round(dy*120))
        if dx:
            self._send(self.HWHEEL, data=round(dx*120))

    def diagnostic(self):
        pid = DWORD()
        window = self.user32.GetForegroundWindow()
        if window:
            self.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        return {"pointer": list(self.position()), "left_pressed": bool(self.user32.GetAsyncKeyState(1) & 0x8000),
                "frontmost_app": "pid:"+str(pid.value) if pid.value else None}
