# 仅在 GitHub 的一次性 Windows 桌面验证安装、运行、重装和卸载。
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:MOUSE_ASSISTANT_CI_SMOKE -ne '1') {
    throw 'Installer integration test is restricted to the explicitly enabled CI desktop'
}

function Invoke-CheckedProcess {
    param([string]$File, [string[]]$Arguments, [int]$TimeoutSeconds = 180)
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $process.Kill()
        throw "Process timed out: $File"
    }
    if ($process.ExitCode -ne 0) { throw "Process failed ($($process.ExitCode)): $File" }
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Runtime.InteropServices.ComTypes;
public static class InstallerPathCheck {
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
  public static extern uint GetLongPathName(string path, StringBuilder buffer, uint length);
  [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
  private class ShellLink { }
  [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  private interface IShellLinkW {
    [PreserveSig]
    int GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int length, IntPtr data, uint flags);
  }
  public static string ReadShortcut(string path) {
    object link = new ShellLink();
    try {
      ((IPersistFile)link).Load(path, 0);
      var target = new StringBuilder(32768);
      Marshal.ThrowExceptionForHR(((IShellLinkW)link).GetPath(target, target.Capacity, IntPtr.Zero, 4));
      return target.ToString();
    } finally { Marshal.FinalReleaseComObject(link); }
  }
}
'@
function Get-CanonicalPath([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "Shortcut target does not exist: $Path" }
    $buffer = New-Object System.Text.StringBuilder 32768
    $length = [InstallerPathCheck]::GetLongPathName($Path, $buffer, 32768)
    if ($length -eq 0 -or $length -ge 32768) { throw "Cannot resolve path: $Path" }
    return [IO.Path]::GetFullPath($buffer.ToString())
}

$report = @{ passed = $false; installer = 'NSIS'; version = (Get-Content VERSION -Raw).Trim() }
$installer = (Resolve-Path 'dist-release/MouseActionAssistant-windows-x64-setup.exe').Path
$installDir = Join-Path $env:RUNNER_TEMP ('Mouse 安装测试 ' + [guid]::NewGuid().ToString('N'))
$registry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant'
$dataDir = Join-Path $env:LOCALAPPDATA 'MouseActionAssistant\recordings'
$sentinel = Join-Path $dataDir ('installer-preserve-' + [guid]::NewGuid().ToString('N') + '.txt')
$shortcutName = '鼠标动作助手.lnk'
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) $shortcutName
$startShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) $shortcutName

try {
    if ((Test-Path $registry) -or (Test-Path $installDir) -or (Test-Path $desktopShortcut) -or (Test-Path $startShortcut)) {
        throw 'Pre-existing installation detected; test will not modify it'
    }
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    Set-Content -LiteralPath $sentinel -Value 'keep recordings' -Encoding utf8
    # NSIS 要求 /D 位于最后且不加引号，其后的所有字符均属于路径。
    $arguments = @('/S', ('/D=' + $installDir))
    Invoke-CheckedProcess $installer $arguments
    $exe = Join-Path $installDir 'MouseActionAssistant.exe'
    $uninstaller = Join-Path $installDir 'Uninstall.exe'
    foreach ($file in @($exe, $uninstaller, (Join-Path $installDir '_internal\python311.dll'), $desktopShortcut, $startShortcut)) {
        if (-not (Test-Path -LiteralPath $file)) { throw "Missing installed file: $file" }
    }
    $entry = Get-ItemProperty $registry
    if ($entry.DisplayVersion -ne $report.version) { throw 'Installed version does not match VERSION' }
    New-Item -ItemType Directory -Force -Path 'windows-installer-shortcuts' | Out-Null
    Copy-Item -LiteralPath $startShortcut -Destination 'windows-installer-shortcuts/start-menu.lnk'
    Copy-Item -LiteralPath $desktopShortcut -Destination 'windows-installer-shortcuts/desktop.lnk'
    $shortcutTarget = [InstallerPathCheck]::ReadShortcut($startShortcut)
    $report.shortcut_target = $shortcutTarget
    $report.installed_executable = $exe
    Write-Host "Shortcut target: $shortcutTarget"
    Write-Host "Installed executable: $exe"
    if ((Get-CanonicalPath $shortcutTarget) -ne (Get-CanonicalPath $exe)) { throw 'Start menu shortcut has incorrect target' }
    if ((Get-CanonicalPath ([InstallerPathCheck]::ReadShortcut($desktopShortcut))) -ne (Get-CanonicalPath $exe)) { throw 'Desktop shortcut has incorrect target' }
    $report.installed = $true
    $report.shortcuts = $true

    $smokeReport = Join-Path $PWD 'windows-installed-smoke.json'
    Invoke-CheckedProcess $shortcutTarget @('--ci-smoke', ('"' + $smokeReport + '"'))
    $smoke = Get-Content $smokeReport -Raw | ConvertFrom-Json
    if (-not $smoke.passed -or -not $smoke.frozen) { throw 'Installed application native smoke test failed' }
    $report.installed_app_smoke = $true

    # 同版本重新安装不应擦除录制目录。
    Invoke-CheckedProcess $installer $arguments
    if (-not (Test-Path $sentinel)) { throw 'Reinstall removed recording data' }
    $report.reinstall = $true

    Invoke-CheckedProcess $uninstaller @('/S')
    # NSIS 将卸载器复制到临时目录继续执行，因此要等待真正的清理完成。
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while (((Test-Path $exe) -or (Test-Path $uninstaller) -or (Test-Path $registry)) -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 200
    }
    if ((Test-Path $exe) -or (Test-Path $uninstaller) -or (Test-Path $registry) -or (Test-Path $desktopShortcut) -or (Test-Path $startShortcut)) {
        throw 'Uninstall left application, registry entry or shortcuts behind'
    }
    if (-not (Test-Path $sentinel)) { throw 'Uninstall removed recording data' }
    $report.uninstalled = $true
    $report.recordings_preserved = $true
    $report.passed = $true
} catch {
    $report.error = $_.ToString()
    throw
} finally {
    $report | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 'windows-installer-smoke.json'
    if (Test-Path -LiteralPath $sentinel) { Remove-Item -LiteralPath $sentinel }
}
