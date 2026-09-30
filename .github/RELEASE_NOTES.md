## 下载与安装

- **Windows x64**：下载 `windows-x64.zip`，完整解压后运行 `MouseActionAssistant.exe`，不要单独移动 EXE。需要 Microsoft Edge WebView2 Runtime 与 .NET Framework 4.8。
- **Mac Apple Silicon（M 系列）**：下载 `macos-arm64.dmg`，将应用拖入 Applications。也提供 ZIP 格式。
- **SHA256SUMS.txt**：包含安装产物的 SHA-256 校验值。
- **build-info.json**：记录对应源码提交和自动构建地址。

## 使用提醒

回放会控制真实鼠标，不支持后台隔离操作。先在无害场景测试；按 Esc 急停。macOS 需要为当前版本开启输入监控与辅助功能权限；Windows 无法操作更高权限程序或 UAC 安全桌面。

此构建未配置 Windows 代码签名或 Apple Developer ID 签名／公证，操作系统可能显示安全提示。请确认下载来源。
