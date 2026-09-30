"""平台鼠标后端：共享引擎不直接引用 macOS 框架。"""
import sys


def create_backend():
    if sys.platform == "darwin":
        return MacMouseBackend()
    if sys.platform == "win32":
        from windows_mouse import WindowsMouseBackend
        return WindowsMouseBackend()
    raise RuntimeError("目前仅支持 macOS 和 Windows")


class MacMouseBackend:
    def __init__(self):
        import Quartz
        self.q = Quartz
        self.source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)

    def position(self):
        p = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
        return p.x, p.y

    def screen_bounds(self):
        q = self.q
        error, displays, count = q.CGGetActiveDisplayList(32, None, None)
        if error or not count:
            raise RuntimeError("无法读取显示器")
        bounds = [q.CGDisplayBounds(d) for d in displays[:count]]
        x, y = min(b.origin.x for b in bounds), min(b.origin.y for b in bounds)
        return {"x": x, "y": y,
                "width": max(b.origin.x+b.size.width for b in bounds)-x,
                "height": max(b.origin.y+b.size.height for b in bounds)-y}

    def _post(self, event):
        if event is None:
            raise RuntimeError("无法创建鼠标事件")
        self.q.CGEventPost(self.q.kCGHIDEventTap, event)

    def _button(self, name, suffix):
        q = self.q
        prefix, button = {"left": ("Left", q.kCGMouseButtonLeft),
                          "right": ("Right", q.kCGMouseButtonRight),
                          "middle": ("Other", q.kCGMouseButtonCenter)}[name]
        return getattr(q, "kCGEvent"+prefix+"Mouse"+suffix), button

    def move(self, x, y, pressed):
        q = self.q
        kind, button = q.kCGEventMouseMoved, q.kCGMouseButtonLeft
        for name in ("left", "right", "middle"):
            if name in pressed:
                kind, button = self._button(name, "Dragged")
                break
        self._post(q.CGEventCreateMouseEvent(self.source, kind, q.CGPointMake(x, y), button))

    def button(self, x, y, name, pressed, click_count=1):
        q = self.q
        kind, button = self._button(name, "Down" if pressed else "Up")
        event = q.CGEventCreateMouseEvent(self.source, kind, q.CGPointMake(x, y), button)
        if event is None:
            raise RuntimeError("无法创建鼠标事件")
        q.CGEventSetIntegerValueField(event, q.kCGMouseEventClickState, click_count)
        self._post(event)

    def scroll(self, x, y, dx, dy):
        self.move(x, y, set())
        self._post(self.q.CGEventCreateScrollWheelEvent(
            self.source, self.q.kCGScrollEventUnitPixel, 2, int(dy*10), int(dx*10)))

    def diagnostic(self):
        from AppKit import NSWorkspace
        q = self.q
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return {"pointer": list(self.position()), "left_pressed": bool(q.CGEventSourceButtonState(
            q.kCGEventSourceStateCombinedSessionState, q.kCGMouseButtonLeft)),
            "frontmost_app": app.bundleIdentifier() if app else None}
