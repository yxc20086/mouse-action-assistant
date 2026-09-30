"""
macOS 辅助功能 (Accessibility) 与事件权限检测与重置模块
"""
import ctypes
import subprocess
from ctypes import util


def is_accessibility_trusted(prompt_user: bool = False) -> bool:
    """
    检测当前应用是否已获得 macOS 辅助功能权限。
    如果 prompt_user 为 True 且未授权，macOS 会自动弹出系统授权对话框。
    """
    try:
        app_services = ctypes.cdll.LoadLibrary(util.find_library('ApplicationServices'))
        core_foundation = ctypes.cdll.LoadLibrary(util.find_library('CoreFoundation'))

        if prompt_user:
            kAXTrustedCheckOptionPrompt = ctypes.c_void_p.in_dll(
                app_services, 'kAXTrustedCheckOptionPrompt'
            )
            kCFBooleanTrue = ctypes.c_void_p.in_dll(core_foundation, 'kCFBooleanTrue')

            cf_dict_create = core_foundation.CFDictionaryCreate
            cf_dict_create.restype = ctypes.c_void_p
            cf_dict_create.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]

            keys = (ctypes.c_void_p * 1)(kAXTrustedCheckOptionPrompt)
            values = (ctypes.c_void_p * 1)(kCFBooleanTrue)
            options = cf_dict_create(None, keys, values, 1, None, None)

            ax_is_trusted_with_options = app_services.AXIsProcessTrustedWithOptions
            ax_is_trusted_with_options.restype = ctypes.c_bool
            ax_is_trusted_with_options.argtypes = [ctypes.c_void_p]

            trusted = bool(ax_is_trusted_with_options(options))
            core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
            core_foundation.CFRelease(options)
        else:
            ax_is_trusted = app_services.AXIsProcessTrusted
            ax_is_trusted.restype = ctypes.c_bool
            trusted = bool(ax_is_trusted())

        # 监听权限不能证明具备注入点击所需的辅助功能权限。
        return trusted
    except Exception:
        return False


def open_accessibility_settings() -> None:
    """直接打开 macOS 系统设置中的'辅助功能'隐私面板"""
    try:
        subprocess.run(
            [
                'open',
                'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
            ],
            check=False,
        )
    except Exception as e:
        print(f"打开系统设置失败: {e}")


def reset_accessibility_cache() -> None:
    """清除旧版本的 TCC 签名权限缓存，以便系统重新识别最新版本的应用二进制"""
    try:
        subprocess.run(["tccutil", "reset", "Accessibility", "com.mouse.macro.assistant"], check=False)
    except Exception as e:
        print(f"重置权限缓存失败: {e}")


def can_post_events() -> bool:
    """探测当前进程是否真正具备模拟鼠标按键事件的权限（杜绝幽灵授权）"""
    try:
        return is_accessibility_trusted(prompt_user=False)
    except Exception:
        return False
