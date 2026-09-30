"""跨平台构建独立应用。仅写入 build-release / dist-release，不安装或删除旧版本。"""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import re

ROOT = Path(__file__).resolve().parents[1]


def app_version():
    version = (os.environ.get("APP_VERSION") or (ROOT/"VERSION").read_text(encoding="utf-8")).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError("VERSION 文件格式无效")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and os.environ.get("GITHUB_REF_NAME") != "v"+version:
        raise ValueError("版本标签必须与 VERSION 文件一致")
    return version


def find_makensis():
    candidates = [os.environ.get("MAKENSIS_PATH"), shutil.which("makensis.exe"),
                  str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))/"NSIS/makensis.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("请先安装 NSIS 3，或用 MAKENSIS_PATH 指定 makensis.exe")


def uninstall_manifest(source):
    source = Path(source)
    def relative(path):
        return str(path.relative_to(source)).replace("/", "\\").replace("$", "$$")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    directories = sorted((path for path in source.rglob("*") if path.is_dir()),
                         key=lambda path: len(path.parts), reverse=True)
    return "\n".join([f'Delete "$INSTDIR\\{relative(path)}"' for path in files] +
                     [f'RMDir "$INSTDIR\\{relative(path)}"' for path in directories]) + "\n"


def build_windows_zip(output, name="MouseActionAssistant"):
    output = Path(output)
    source = output/name
    archive = output/"MouseActionAssistant-windows-x64.zip"
    if not (source/(name+".exe")).is_file() or not (source/"_internal").is_dir():
        raise RuntimeError("Windows 便携包缺少 EXE 或运行依赖目录")
    if archive.exists():
        raise FileExistsError(f"便携包已存在，不覆盖：{archive}")
    shutil.make_archive(str(archive.with_suffix("")), "zip", root_dir=output, base_dir=name)
    return archive


def main():
    os.chdir(ROOT)
    work, output = ROOT/"build-release", ROOT/"dist-release"
    version = app_version()
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
        print(build_windows_zip(output, name))
        installer = output/"MouseActionAssistant-windows-x64-setup.exe"
        if installer.exists():
            raise FileExistsError(f"安装包已存在，不覆盖：{installer}")
        installer_script = work/"windows-installer.nsi"
        installer_script.write_text((ROOT/"packaging/windows-installer.nsi").read_text(encoding="utf-8"), encoding="utf-8-sig")
        manifest = work/"uninstall-files.nsh"
        manifest.write_text(uninstall_manifest(output/name), encoding="utf-8-sig")
        subprocess.run([find_makensis(), "/DAPP_VERSION="+version,
                        "/DVERSION_NUMERIC="+version.split("-")[0]+".0",
                        "/DSOURCE_DIR="+str(output/name), "/DOUTPUT_FILE="+str(installer),
                        "/DICON_FILE="+str(work/"AppIcon.ico"), "/DUNINSTALL_FILES="+str(manifest),
                        str(installer_script)], check=True)
        if not installer.is_file():
            raise RuntimeError("NSIS 未生成安装包")
        print(installer)
    else:
        app = output/(name+".app")
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        dmg = output/("MouseActionAssistant-macos-"+platform.machine()+".dmg")
        if dmg.exists():
            raise FileExistsError(f"安装包已存在，不覆盖：{dmg}")
        with tempfile.TemporaryDirectory(prefix="mouse-assistant-dmg-") as directory:
            staging = Path(directory)
            subprocess.run(["ditto", str(app), str(staging/app.name)], check=True)
            (staging/"Applications").symlink_to("/Applications")
            subprocess.run(["hdiutil", "create", "-volname", name, "-srcfolder", str(staging),
                            "-format", "UDZO", str(dmg)], check=True)
        subprocess.run(["hdiutil", "verify", str(dmg)], check=True)
        print(dmg)


if __name__ == "__main__":
    main()
