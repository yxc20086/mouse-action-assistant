Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!include "LogicLib.nsh"

Name "鼠标动作助手"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\MouseActionAssistant"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "${VERSION_NUMERIC}"
VIAddVersionKey "ProductName" "鼠标动作助手"
VIAddVersionKey "FileDescription" "鼠标动作助手安装程序"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "mouse-action-assistant contributors"
!define MUI_ABORTWARNING
!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\MouseActionAssistant.exe"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "需要 64 位 Windows 10 或以上版本。"
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "需要 Windows 10 或以上版本。"
    Abort
  ${EndIf}
  SetRegView 64
  SetShellVarContext current
FunctionEnd

Section "程序文件和开始菜单快捷方式（必选）" MainSection
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\鼠标动作助手.lnk" "$INSTDIR\MouseActionAssistant.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "DisplayName" "鼠标动作助手"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "Publisher" "mouse-action-assistant"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "DisplayIcon" "$INSTDIR\MouseActionAssistant.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "URLInfoAbout" "https://github.com/yxc20086/mouse-action-assistant"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant" "NoRepair" 1
SectionEnd

Section "桌面快捷方式" DesktopSection
  CreateShortcut "$DESKTOP\鼠标动作助手.lnk" "$INSTDIR\MouseActionAssistant.exe"
SectionEnd

Function un.onInit
  SetRegView 64
  SetShellVarContext current
FunctionEnd

Section "Uninstall"
  ; 由构建脚本生成精确文件清单，不递归删除用户选择的整个安装目录。
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$SMPROGRAMS\鼠标动作助手.lnk"
  Delete "$DESKTOP\鼠标动作助手.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MouseActionAssistant"
  RMDir "$INSTDIR"
  ; 录制目录位于另一处 LOCALAPPDATA\MouseActionAssistant，卸载不访问它。
SectionEnd
