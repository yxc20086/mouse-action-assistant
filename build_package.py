"""
自动化构建脚本：构建 macOS 独立 App 与 DMG 安装包 (PRO 版)
"""
import os
import shutil
import subprocess
import sys


def clean_build_artifacts():
    """清理历史构建文件"""
    for folder in ["build", "dist", "dmg_staging", "__pycache__"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    for f in ["鼠标路径助手-安装包.dmg", "鼠标路径助手.spec", "鼠标路径助手 PRO.spec"]:
        if os.path.exists(f):
            os.remove(f)


def build_app():
    """使用 PyInstaller 构建独立 .app 应用程序"""
    print("▶ 正在通过 PyInstaller 编译为 macOS 独立 .app 应用程序...")

    pyinstaller_bin = os.path.join(os.path.dirname(__file__), "venv", "bin", "pyinstaller")
    if not os.path.exists(pyinstaller_bin):
        pyinstaller_bin = "pyinstaller"

    cmd = [
        pyinstaller_bin,
        "--noconfirm",
        "--windowed",
        "--name=鼠标路径助手",
        "--icon=AppIcon.icns",
        "--add-data=ui:ui",
        "--hidden-import=webview",
        "--hidden-import=webview.platforms.cocoa",
        "--hidden-import=pynput.mouse._darwin",
        "--hidden-import=pynput.keyboard._darwin",
        "--hidden-import=bottle",
        "--hidden-import=proxy_tools",
        "--osx-bundle-identifier=com.mouse.macro.assistant",
        "app.py",
    ]

    subprocess.run(cmd, check=True)

    app_path = os.path.join("dist", "鼠标路径助手.app")
    if not os.path.exists(app_path):
        raise FileNotFoundError(f"未找到生成的 App: {app_path}")

    # 更新 Info.plist 补充权限描述
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    if os.path.exists(plist_path):
        print("▶ 注入 macOS 权限描述到 Info.plist...")
        plist_buddy = "/usr/libexec/PlistBuddy"
        entries = [
            ("CFBundleDisplayName", "string", "鼠标路径助手"),
            ("NSAccessibilityUsageDescription", "string", "需要辅助功能权限以录制并重现鼠标动作与轨迹。"),
            ("NSAppleEventsUsageDescription", "string", "需要系统事件权限以执行鼠标宏回放。"),
            ("NSHighResolutionCapable", "bool", "true"),
        ]
        for key, ktype, val in entries:
            subprocess.run([plist_buddy, "-c", f"Delete :{key}", plist_path], stderr=subprocess.DEVNULL)
            subprocess.run([plist_buddy, "-c", f"Add :{key} {ktype} {val}", plist_path], check=True)

    # 确保 ui 资源在 Contents/Resources 和 Contents/MacOS 目录双向就绪
    res_ui = os.path.join(app_path, "Contents", "Resources", "ui")
    macos_ui = os.path.join(app_path, "Contents", "MacOS", "ui")
    os.makedirs(res_ui, exist_ok=True)
    os.makedirs(macos_ui, exist_ok=True)
    subprocess.run(["cp", "-R", "ui/.", res_ui], check=True)
    subprocess.run(["cp", "-R", "ui/.", macos_ui], check=True)

    # 重新进行本地 ad-hoc 签名，避免 macOS Apple Silicon 校验报 Info.plist 被篡改
    print("▶ 执行本地 Ad-hoc 代码签名...")
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app_path], check=True)

    print("✔ .app 应用程序打包完成！")
    return app_path


def build_dmg(app_path: str):
    """打包为标准 macOS DMG 拖拽安装镜像"""
    print("▶ 正在创建标准 macOS DMG 拖拽安装镜像...")

    staging_dir = "dmg_staging"
    os.makedirs(staging_dir, exist_ok=True)

    target_app = os.path.join(staging_dir, "鼠标路径助手.app")
    # 拷贝 app 到暂存目录
    subprocess.run(["cp", "-R", app_path, target_app], check=True)

    # 创建指向 /Applications 的软链接
    apps_link = os.path.join(staging_dir, "Applications")
    if os.path.exists(apps_link) or os.path.islink(apps_link):
        os.remove(apps_link)
    os.symlink("/Applications", apps_link)

    dmg_output = "鼠标路径助手-安装包.dmg"
    if os.path.exists(dmg_output):
        os.remove(dmg_output)

    # 调用 hdiutil 制作压缩格式的 UDZO 镜像
    dmg_cmd = [
        "hdiutil",
        "create",
        "-volname", "鼠标路径助手",
        "-srcfolder", staging_dir,
        "-ov",
        "-format", "UDZO",
        dmg_output,
    ]
    subprocess.run(dmg_cmd, check=True)

    # 清理暂存目录
    shutil.rmtree(staging_dir)
    print(f"✔ DMG 安装包生成成功: {dmg_output}")
    return dmg_output


def main():
    clean_build_artifacts()
    app_path = build_app()
    dmg_path = build_dmg(app_path)

    # 自动同步部署到系统 /Applications/
    apps_target = "/Applications/鼠标路径助手.app"
    print(f"▶ 正在同步安装到系统应用目录: {apps_target} ...")
    if os.path.exists(apps_target):
        shutil.rmtree(apps_target)
    subprocess.run(["cp", "-R", app_path, apps_target], check=True)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", apps_target], check=True)

    print("\n🎉 全部打包与部署任务完成！")
    print(f"1. 独立程序: {os.path.abspath(app_path)}")
    print(f"2. 安装镜像: {os.path.abspath(dmg_path)}")
    print(f"3. 应用程序: {apps_target} (已就绪并已签名)")


if __name__ == "__main__":
    main()
