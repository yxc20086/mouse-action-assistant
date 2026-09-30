; 使用 scripts/build.py 传入路径和版本，不依赖开发机器的固定目录。
#ifndef MyAppVersion
  #error MyAppVersion is required
#endif
#ifndef SourceDir
  #error SourceDir is required
#endif
#ifndef OutputPath
  #error OutputPath is required
#endif
#ifndef IconPath
  #error IconPath is required
#endif

[Setup]
AppId={{5F39376B-3069-40B4-A8C2-F3C819D76892}
AppName=鼠标动作助手
AppVersion={#MyAppVersion}
AppPublisher=mouse-action-assistant
AppSupportURL=https://github.com/yxc20086/mouse-action-assistant
AppUpdatesURL=https://github.com/yxc20086/mouse-action-assistant/releases
DefaultDirName={localappdata}\Programs\MouseActionAssistant
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=MouseActionAssistant-windows-x64-setup
SetupIconFile={#IconPath}
UninstallDisplayIcon={app}\MouseActionAssistant.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=MouseActionAssistant.exe
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\鼠标动作助手"; Filename: "{app}\MouseActionAssistant.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\鼠标动作助手"; Filename: "{app}\MouseActionAssistant.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\MouseActionAssistant.exe"; Description: "{cm:LaunchProgram,鼠标动作助手}"; Flags: nowait postinstall skipifsilent

; 不添加 UninstallDelete：录制数据在 LOCALAPPDATA\MouseActionAssistant，
; 与安装目录分离，卸载只清理本安装包登记的程序文件和快捷方式。
[Code]
function HasWebView2: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKCU, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'))
    or (RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'))
    or (RegQueryStringValue(HKLM64, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if (not HasWebView2) and (not WizardSilent) then
    MsgBox('This application needs Microsoft Edge WebView2 Runtime. If it is not installed, please install it before launching the application.' + #13#10 +
      'https://developer.microsoft.com/microsoft-edge/webview2/', mbInformation, MB_OK);
end;
