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

下载 `MouseActionAssistant-版本号-windows-x64-setup.exe`，双击按向导安装，不需要手动解压或安装 Python。可以选择安装目录、添加桌面快捷方式；安装后从开始菜单启动“鼠标动作助手”。

也提供同版本 `MouseActionAssistant-版本号-windows-x64.zip` 免安装版：完整解压后运行里面的 `MouseActionAssistant.exe`，不要单独移动 EXE 或删除 `_internal`。从 `v1.0.2` 开始，每个版本同时保留 ZIP 与安装 EXE。

两种版本功能相同，都不需要安装 Python，并共用当前用户的录制目录；请只运行其中一个。ZIP 是免安装形式，不表示录制数据随程序文件夹移动。

安装版默认按当前用户安装到 `%LOCALAPPDATA%\Programs\MouseActionAssistant`，不自动申请管理员权限。在 Windows“设置 → 应用”中可卸载；卸载保留录制记录。安装或升级前请先停止录制／回放并退出程序，避免丢失尚未保存的操作。历史发布附件保留，不覆盖旧文件。

需要 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) 和 .NET Framework 4.8（Windows 10/11 通常已具备）。缺少运行时时应用会提示启动失败；本安装包不静默安装或修改这些系统运行时。

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

Windows CI 另有显式启用的 `--ci-smoke` 原生测试：在专用测试窗口里录制、回放左右键／中键、拖拽和滚动，验证 Esc 释放按键、中文记录管理、WebView2 界面与打包后的重启辅助进程。安装包还会在 CI 实际静默安装到含中文和空格的目录，验证快捷方式、已安装程序运行、重新安装、卸载和记录保留。不要在日常桌面手动运行这些测试，它们会操作真实鼠标并执行安装／卸载。CI 结果不能覆盖所有第三方软件、不同权限级别或多屏布局。

在 Windows 本地运行单元测试时，将上面的 Python 命令替换为 `.\venv\Scripts\python.exe`。

## 自动与本地构建

推送到 `main` 自动运行 GitHub Actions，也可在仓库 **Actions → Build desktop apps → Run workflow** 手动触发。构建成功后，在对应运行的 **Artifacts** 下载 Windows x64 ZIP/安装 EXE、macOS arm64 ZIP/DMG 或带校验文件的 `release-bundle`。ZIP 会先解压并实测运行，安装 EXE 会验证安装、运行和卸载。GitHub Actions 的附件下载界面可能仍用 ZIP 包装附件；正式 Releases 提供单独下载的 ZIP 和安装 EXE。普通分支构建只生成快照包，不创建正式 Release。

### 在 GitHub 网页一键打包发布

无需本地终端，也无需先编辑 `VERSION`：

1. 打开仓库 **Actions → Build desktop apps → Run workflow**。
2. 分支选 **main**。
3. 在“版本号”填写未使用过的版本，例如 **1.0.4**（也接受 `v1.0.4`）。
4. 多行说明先按[版本 Markdown 编辑指南](release-notes/README.md)保存为 `release-notes/版本号.md`；Run workflow 的 **“单行简述”** 留空即可自动读取该文件。仅简短单行内容才直接填写小框，**不要在小框中按 Enter**。
5. 勾选 **“发布到 Releases”**，再点击绿色 **Run workflow**。
6. 等“Publish GitHub Release”成功后，去 [Releases](https://github.com/yxc20086/mouse-action-assistant/releases) 下载 ZIP 或安装包。

不勾选发布时只打包，产物放在该次运行的 **Artifacts → release-bundle**；版本号可留空。GitHub 的原生表单不支持多行输入，按 Enter 可能直接提交；请在 Markdown 文件编辑器中换行，发布表单填写完后用鼠标点击按钮。网页填写的版本覆盖本次构建的应用版本，并写入安装包和 `build-info.json`，但不会改写 `main` 分支的 `VERSION` 文件。该文件继续作为本地/普通推送构建的默认版本。

流程先检查版本号是否已存在，再运行双平台测试与打包。只有构建和校验全部通过，才给本次被测试的提交创建标签并公开发布；使用 GitHub 自带令牌创建的标签不会重复触发一轮构建。已存在的标签或 Release（含草稿）会直接拒绝，绝不覆盖旧版本。

手动任务使用独立队列，不与普通推送或其他手动任务相互取消。若同时提交同一个新版本，最终的原子标签创建只允许一个成功，另一个会拒绝发布而不是覆盖。

### 发布页的更新内容

- 填写“单行简述”时，优先显示填写的内容（最多 10000 字符），不会混入自动提交列表。
- 小框留空时，先读取本次版本对应的 `release-notes/版本号.md`（也支持带 `v` 的文件名），保留其中的换行、列表和 Markdown 标题。
- 小框留空且没有对应文件时，查找当前提交历史中最近发布的版本，汇总之后的提交标题及链接，并附完整版本对比链接。正式版本会跳过预发布版本和草稿。
- 首次发布展示提交历史；同一提交重新发不同版本时，会明确写明没有新增代码提交，不编造更新内容。
- 提交较多时最多展示 200 条，并提供完整历史/对比链接。更新内容放在发布页上方，安装说明保留在下方。
- 每次打包都会生成 **Artifacts → release-notes-preview**，可先不勾选发布来查看说明预览。正式发布时按当时可用的历史发布重新生成；已经发布的旧版本说明不会被本配置自动修改。

### 通过 Git 标签自动发布

也可以在本地为已经提交的代码创建版本标签：

```bash
git pull --ff-only
git tag v1.0.4
git push origin v1.0.4
```

标签推送后将使用标签中的版本号执行 Windows/macOS 测试与构建；**两平台全部通过、产物齐全且校验通过后**，才自动创建 [GitHub Release](https://github.com/yxc20086/mouse-action-assistant/releases)。发布步骤再次确认标签仍指向本次测试的提交，避免标签移动导致产物与源码不一致。

- 正式版本：`v1.0.0`、`v1.0.1` 等。
- 预发布：`v1.1.0-rc.1` 等带后缀标签，会标记为 Pre-release，不标记为 Latest。
- 不要重复使用已发布的版本号；流程不会覆盖或删除已有 Release 附件。
- 网页不勾选“发布到 Releases”时，只构建，不发布，即使分支下拉框选的是标签。
- 如果发布中断后标签或草稿已创建，重跑不会自动覆盖；先检查已生成的 Release/日志，必要时使用新的版本号。
- 不需要配置个人访问令牌；仅发布任务使用 GitHub 自动提供的 `GITHUB_TOKEN` 与 `contents: write` 权限。如果组织策略禁止写入，请由仓库管理员调整 Actions 权限。

每次 Release 包含带版本号的 Windows ZIP 和安装 EXE、macOS ZIP 和 DMG，以及 `SHA256SUMS.txt`、`build-info.json`。四个程序产物必须齐全且验证通过才会发布。实际发布不会附带用户的录制或诊断数据。

本地使用平台原生 Python 执行（Windows 用 `.\venv\Scripts\python.exe`）：

```bash
./venv/bin/python3 -m pip install -r requirements-dev.txt
./venv/bin/python3 scripts/build.py
```

本地默认读取 `VERSION`；如需重建特定发布版本，可设置 `APP_VERSION` 环境变量覆盖，例如 macOS 上 `APP_VERSION=1.0.3 ./venv/bin/python3 scripts/build.py`，PowerShell 上先执行 `$env:APP_VERSION='1.0.3'`。

Windows 构建机还需要 NSIS 3（可通过 `MAKENSIS_PATH` 指定 `makensis.exe`）；GitHub Windows 构建机已自带。Windows 产物为 `dist-release/MouseActionAssistant/`、`dist-release/MouseActionAssistant-windows-x64.zip` 与 `dist-release/MouseActionAssistant-windows-x64-setup.exe`，macOS 产物为 `dist-release/鼠标动作助手.app` 与对应架构的 DMG。不能在 macOS 上直接交叉生成 Windows EXE。

新的构建脚本不安装到系统目录，也不自动删除旧产物。旧的 `build_package.py` 会清理旧构建并覆盖本机应用，保留供参考，不用于当前跨平台构建。
