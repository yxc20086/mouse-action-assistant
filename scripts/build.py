"""跨平台构建独立应用。仅写入 build-release / dist-release，不安装或删除旧版本。"""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    work, output = ROOT/"build-release", ROOT/"dist-release"
    work.mkdir(exist_ok=True)
    name = "MouseActionAssistant" if sys.platform == "win32" else "鼠标动作助手"
    args = [sys.executable, "-m", "PyInstaller", "--windowed", "--name="+name,
            "--distpath="+str(output), "--workpath="+str(work), "--specpath="+str(work),
            "--add-data="+str(ROOT/"ui")+os.pathsep+"ui",
            "--hidden-import=bottle", "--hidden-import=proxy_tools"]
    if sys.platform == "win32":
        from PIL import Image
        icon = work/"AppIcon.ico"
        Image.open(ROOT/"AppIcon.iconset/icon_256x256.png").save(icon, sizes=[(16,16),(32,32),(48,48),(256,256)])
        args.extend(["--icon="+str(icon), "--manifest="+str(ROOT/"packaging/windows.manifest"),
                     "--hidden-import=webview.platforms.winforms", "--hidden-import=webview.platforms.edgechromium",
                     "--hidden-import=pynput.mouse._win32", "--hidden-import=pynput.keyboard._win32"])
    elif sys.platform == "darwin":
        args.extend(["--icon="+str(ROOT/"AppIcon.icns"), "--osx-bundle-identifier=com.mouse.macro.assistant",
                     "--hidden-import=webview.platforms.cocoa", "--hidden-import=pynput.mouse._darwin",
                     "--hidden-import=pynput.keyboard._darwin"])
    else:
        raise SystemExit("Only Windows and macOS builds are supported")
    args.append(str(ROOT/"app.py"))
    subprocess.run(args, check=True)
    if sys.platform == "win32":
        shutil.make_archive(str(output/"MouseActionAssistant-windows-x64"), "zip", root_dir=output, base_dir=name)
        print(output/"MouseActionAssistant-windows-x64.zip")
    else:
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(output/(name+".app"))], check=True)
        print(output/(name+".app"))


if __name__ == "__main__":
    main()
