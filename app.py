"""
鼠标路径助手 PRO - 主启动入口
采用 macOS 原生 WebKit 渲染超高质感毛玻璃界面与硬件加速 Canvas 雷达
"""
import os
import sys


def get_ui_content() -> str:
    """
    寻找并读取 UI 资源，支持源码运行与 PyInstaller 打包环境。
    将 HTML、CSS、JS 整合为单一自包含内容直接载入 WebKit，
    避免任何路径错误或本地 file:// 协议沙盒限制。
    """
    candidates = [
        # 1. macOS 应用程序 Bundle 内部 Resources/ui 目录
        os.path.join(os.path.dirname(sys.executable), "..", "Resources", "ui"),
        # 2. 与可执行文件同级的 ui 目录
        os.path.join(os.path.dirname(sys.executable), "ui"),
        # 3. PyInstaller 单文件解压目录
        os.path.join(getattr(sys, "_MEIPASS", ""), "ui") if hasattr(sys, "_MEIPASS") else "",
        # 4. 源码所在目录下的 ui 目录
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui"),
        # 5. 当前工作路径下的 ui 目录
        os.path.join(os.getcwd(), "ui"),
    ]

    ui_dir = None
    for cand in candidates:
        if cand and os.path.exists(os.path.join(cand, "index.html")):
            ui_dir = os.path.abspath(cand)
            break

    if not ui_dir:
        raise FileNotFoundError(f"未找到 UI 资源目录，已检索候选路径: {candidates}")

    # 读取并内嵌资源，确保 100% 独立稳定渲染
    with open(os.path.join(ui_dir, "index.html"), "r", encoding="utf-8") as f:
        html = f.read()

    css_path = os.path.join(ui_dir, "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>\n{css}\n</style>")

    js_path = os.path.join(ui_dir, "app.js")
    if os.path.exists(js_path):
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()
        html = html.replace('<script src="app.js"></script>', f"<script>\n{js}\n</script>")

    return html


def main():
    from platform_support import configure_dpi
    configure_dpi()
    import webview
    from api import JsBridgeAPI
    api = JsBridgeAPI()
    html_content = get_ui_content()

    window = webview.create_window(
        title="鼠标动作助手",
        html=html_content,
        js_api=api,
        width=740,
        height=760,
        min_size=(680, 680),
        background_color="#0B0D14",
        text_select=False,
    )
    api.set_window(window)

    # 启动 WebKit 运行循环
    options = {}
    if sys.platform == "win32":
        from platform_support import recordings_directory
        cache = recordings_directory().parent / "webview"
        cache.mkdir(parents=True, exist_ok=True)
        options["storage_path"] = str(cache)
    webview.start(gui="edgechromium" if sys.platform == "win32" else None, debug=False, **options)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restart-helper":
        from app_restart import run_windows_helper
        raise SystemExit(run_windows_helper(sys.argv[2:]))
    if os.environ.get("MOUSE_ASSISTANT_CI_SMOKE") == "1" and len(sys.argv) == 3:
        if sys.argv[1] == "--ci-smoke":
            from windows_smoke import run
            raise SystemExit(run(sys.argv[2]))
        if sys.argv[1] == "--ci-probe":
            from pathlib import Path
            Path(sys.argv[2]).write_text("started")
            raise SystemExit(0)
    try:
        main()
    except Exception as error:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                "启动失败："+str(error)+"\n请安装 Microsoft Edge WebView2 Runtime，并确保程序目录中的 _internal 文件夹完整。",
                "鼠标动作助手", 0x10)
        raise
