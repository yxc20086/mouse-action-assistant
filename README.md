# 鼠标动作助手

Windows / macOS 鼠标动作录制与循环回放工具。共享 Python、pynput 与 pywebview 界面，Windows 使用 Win32 SendInput，macOS 使用 Quartz。

## 功能

- 记录鼠标路径、左右键／中键按下与松开、滚轮操作。
- 录制结束自动保存；记录支持选择、回放、改名、删除和时间显示。
- 支持循环次数、无限循环、倍速、启动倒计时及轮次间隔。
- 开始录制自动最小化，停止后恢复窗口；回放可选择自动最小化。
- 支持 JSON 导入导出、权限检测和手动重启应用以使授权生效。
- 固定窗口布局，仅录制记录列表滚动。

**回放会控制系统真实鼠标，不支持后台隔离操作。** 请在倒计时内切换到目标窗口，保持位置、尺寸和界面内容与录制时一致。先用无害操作验证，避免在删除、提交或支付等不可撤销场景中直接运行宏。

## 环境与启动

支持 Windows 10/11 64 位和 macOS。源码需要 Python 3.9 或以上，自动构建使用 Python 3.11；界面测试需要 Node.js 18 或以上。

### Windows

下载自动构建的 `MouseActionAssistant-windows-x64.zip`，**完整解压后**运行 `MouseActionAssistant.exe`。不要只复制 EXE，旁边的 `_internal` 目录也是运行所需文件。独立版不需要安装 Python。

需要 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) 和 .NET Framework 4.8（Windows 10/11 通常已具备）。缺少 WebView2 时程序会提示启动失败。

源码启动（PowerShell）：

```powershell
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

也可以双击 `start.bat`。Windows 界面不会显示 macOS 授权开关：普通权限可操作同级或较低权限应用；无法操作管理员级别程序、锁屏或 UAC 安全桌面。确需操作管理员程序时，应由用户以相同权限级别启动助手；程序不自动提权。

Windows 采用每显示器 DPI 感知和物理像素坐标。更改缩放、分辨率或显示器排列后，请重新录制；不同电脑或系统间的坐标记录不保证能原样回放。

### macOS

GUI 使用系统 WebKit，依赖中的 Apple 框架只在 macOS 安装。

```bash
python3 -m venv venv
./venv/bin/python3 -m pip install -r requirements.txt
./venv/bin/python3 app.py
```

也可以使用 `./start.sh`。两平台的当前界面入口都是 `app.py`；`main.py`、`recorder.py`、`player.py`、`hotkey_manager.py` 是保留的早期 Tkinter 实现，不是当前主入口，也不用于跨平台构建。

## macOS 授权

在“系统设置 → 隐私与安全性”中，为实际运行的应用开启：

- **输入监控**：录制其他应用里的鼠标动作。
- **辅助功能**：监听快捷键及模拟鼠标动作。

源码运行时需要授权运行 Python 的终端或宿主应用。独立 App 请安装到“应用程序”后启动，不要混用多个旧版本。界面里的权限按钮分别显示当前进程的检测结果；系统开关已开启但当前进程未生效时，请停止操作后使用“重启应用使授权生效”。重启不会修改或重置系统授权。

本地临时签名的 App 更新后可能需要重新授权；此项目未提供 Apple Developer ID 签名或公证，Windows 版也未配置代码签名证书。

## 快捷键

| 快捷键 | 操作 |
| --- | --- |
| F7 / Ctrl+R | 开始或停止录制 |
| F8 / Ctrl+P | 开始或停止回放 |
| Esc | 停止倒计时或回放 |

回放也支持屏幕左上角急停。建议用 F7 停止录制，避免把工具自身的停止按钮录进去。Mac 功能键设置不同，可能需要同时按 Fn。

## 数据与隐私

记录保存在当前用户的独立数据目录，不受应用升级影响：

```text
Windows: %LOCALAPPDATA%\MouseActionAssistant\recordings\
macOS:   ~/Library/Application Support/com.mouse.macro.assistant/recordings/
```

删除记录需要确认；已保存文件会移到该目录下的 `.trash/`，不会删除其他记录或已导出的 JSON。删除失败时原记录保留。仅暂存在内存且尚未落盘的记录删除后无法恢复。

导出操作可能同时生成 `.diagnostics.json`，含录制时的前台应用标识、鼠标坐标、权限状态和进程信息。分享前请自行检查。仓库只包含源码、图标和测试，不包含个人录制、诊断数据、虚拟环境或安装包。

## 测试

```bash
./venv/bin/python3 -m unittest discover -s tests -v
node tests/test_ui.cjs
node --check ui/app.js
```

上述单元测试使用模拟鼠标依赖，不操作真实鼠标。重启测试仅使用临时子进程，不重启用户应用。界面测试是 DOM 契约检查。

Windows CI 另有显式启用的 `--ci-smoke` 原生测试：在专用测试窗口里录制、回放左右键／中键、拖拽和滚动，验证 Esc 释放按键、中文记录管理、WebView2 界面与打包后的重启辅助进程。不要在日常桌面手动运行该测试，它会操作真实鼠标。CI 结果不能覆盖所有第三方软件、不同权限级别或多屏布局。

在 Windows 本地运行单元测试时，将上面的 Python 命令替换为 `.\venv\Scripts\python.exe`。

## 自动与本地构建

推送到 `main` 自动运行 GitHub Actions，也可在仓库 **Actions → Build desktop apps → Run workflow** 手动触发。构建成功后，在对应运行的 **Artifacts** 下载 Windows x64 ZIP、macOS arm64 ZIP/DMG 或带校验文件的 `release-bundle`。普通分支构建只生成快照包，不创建正式 Release。

### 自动发布到 GitHub Releases

先确保想发布的代码已经提交并推送，然后为它创建版本标签，例如：

```bash
git pull --ff-only
git tag v1.0.0
git push origin v1.0.0
```

标签推送后将重新执行 Windows/macOS 测试与构建；**两平台全部通过、产物齐全且校验通过后**，才自动创建 [GitHub Release](https://github.com/yxc20086/mouse-action-assistant/releases)。发布步骤再次确认标签仍指向本次测试的提交，避免标签移动导致产物与源码不一致。

- 正式版本：`v1.0.0`、`v1.0.1` 等。
- 预发布：`v1.1.0-rc.1` 等带后缀标签，会标记为 Pre-release，不标记为 Latest。
- 不要重复使用已发布的版本号；流程不会覆盖或删除已有 Release 附件。
- 从 `main` 手动点 Run workflow 只构建，不发布；选择已有版本标签手动运行会进入发布流程。
- 不需要配置个人访问令牌；仅发布任务使用 GitHub 自动提供的 `GITHUB_TOKEN` 与 `contents: write` 权限。如果组织策略禁止写入，请由仓库管理员调整 Actions 权限。

每次 Release 包含带版本号的 Windows ZIP、macOS ZIP 和 DMG，以及 `SHA256SUMS.txt`、`build-info.json`。实际发布不会附带用户的录制或诊断数据。

本地使用平台原生 Python 执行（Windows 用 `.\venv\Scripts\python.exe`）：

```bash
./venv/bin/python3 -m pip install -r requirements-dev.txt
./venv/bin/python3 scripts/build.py
```

Windows 产物位于 `dist-release/MouseActionAssistant/` 与 `dist-release/MouseActionAssistant-windows-x64.zip`，macOS 产物为 `dist-release/鼠标动作助手.app` 与对应架构的 DMG。不能在 macOS 上直接交叉生成 Windows EXE。

新的构建脚本不安装到系统目录，也不自动删除旧产物。旧的 `build_package.py` 会清理旧构建并覆盖本机应用，保留供参考，不用于当前跨平台构建。
