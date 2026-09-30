# 鼠标动作助手

macOS 鼠标动作录制与循环回放工具，使用 Python、pynput、Quartz 和 pywebview 构建。

## 功能

- 记录鼠标路径、左右键／中键按下与松开、滚轮操作。
- 录制结束自动保存；记录支持选择、回放、改名、删除和时间显示。
- 支持循环次数、无限循环、倍速、启动倒计时及轮次间隔。
- 开始录制自动最小化，停止后恢复窗口；回放可选择自动最小化。
- 支持 JSON 导入导出、权限检测和手动重启应用以使授权生效。
- 固定窗口布局，仅录制记录列表滚动。

**回放会控制系统真实鼠标，不支持后台隔离操作。** 请在倒计时内切换到目标窗口，保持位置、尺寸和界面内容与录制时一致。先用无害操作验证，避免在删除、提交或支付等不可撤销场景中直接运行宏。

## 环境与启动

需要 macOS、Python 3.9 或以上。当前在 Apple Silicon Mac 上开发验证；GUI 使用系统 WebKit。运行测试脚本还需要 Node.js（建议 18 或以上）。

```bash
python3 -m venv venv
./venv/bin/python3 -m pip install -r requirements.txt
./venv/bin/python3 app.py
```

也可以使用 `./start.sh`。当前界面入口是 `app.py`；`main.py`、`recorder.py`、`player.py`、`hotkey_manager.py` 是保留的早期 Tkinter 实现，不是当前主入口。

## macOS 授权

在“系统设置 → 隐私与安全性”中，为实际运行的应用开启：

- **输入监控**：录制其他应用里的鼠标动作。
- **辅助功能**：监听快捷键及模拟鼠标动作。

源码运行时需要授权运行 Python 的终端或宿主应用。独立 App 请安装到“应用程序”后启动，不要混用多个旧版本。界面里的权限按钮分别显示当前进程的检测结果；系统开关已开启但当前进程未生效时，请停止操作后使用“重启应用使授权生效”。重启不会修改或重置系统授权。

本地临时签名的 App 更新后可能需要重新授权；此项目未提供 Apple Developer ID 签名或公证。

## 快捷键

| 快捷键 | 操作 |
| --- | --- |
| F7 / Ctrl+R | 开始或停止录制 |
| F8 / Ctrl+P | 开始或停止回放 |
| Esc | 停止倒计时或回放 |

回放也支持屏幕左上角急停。建议用 F7 停止录制，避免把工具自身的停止按钮录进去。Mac 功能键设置不同，可能需要同时按 Fn。

## 数据与隐私

记录保存在当前用户的：

```text
~/Library/Application Support/com.mouse.macro.assistant/recordings/
```

删除记录需要确认；已保存文件会移到该目录下的 `.trash/`，不会删除其他记录或已导出的 JSON。删除失败时原记录保留。仅暂存在内存且尚未落盘的记录删除后无法恢复。

导出操作可能同时生成 `.diagnostics.json`，含录制时的前台应用标识、鼠标坐标、权限状态和进程信息。分享前请自行检查。仓库只包含源码、图标和测试，不包含个人录制、诊断数据、虚拟环境或安装包。

## 测试

```bash
./venv/bin/python3 -m unittest discover -s tests -v
node tests/test_ui.cjs
node --check ui/app.js
```

鼠标测试使用模拟依赖，不操作真实鼠标。重启测试仅使用临时子进程，不重启用户应用。界面测试是 DOM 契约检查，不代替 macOS 实机视觉与权限验证。

## 构建独立 App

```bash
./venv/bin/python3 -m pip install -r requirements-dev.txt
./venv/bin/python3 -m PyInstaller \
  --windowed --name=鼠标动作助手 \
  --distpath=dist-release --workpath=build-release \
  --icon=AppIcon.icns --add-data=ui:ui \
  --hidden-import=webview.platforms.cocoa \
  --hidden-import=pynput.mouse._darwin \
  --hidden-import=pynput.keyboard._darwin \
  --hidden-import=bottle --hidden-import=proxy_tools \
  --osx-bundle-identifier=com.mouse.macro.assistant app.py
```

产物位于 `dist-release/鼠标动作助手.app`。旧的 `build_package.py` 会清理旧构建并覆盖安装到应用程序目录，保留供参考，不建议直接用于当前版本。
