"""在旧进程退出后重新打开当前应用，不启动其他同名版本。"""
import os
from pathlib import Path
import subprocess
import sys
import json


def restart_command():
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            if not executable.is_file():
                raise RuntimeError("找不到当前可执行文件")
            return [str(executable)]
        bundle = executable.parent.parent.parent
        if bundle.suffix != ".app" or not (bundle / "Contents/Info.plist").is_file():
            raise RuntimeError("无法确认当前应用位置，请手动退出后重新打开")
        return ["/usr/bin/open", "-n", str(bundle)]
    source = Path(__file__).resolve().with_name("app.py")
    if not source.is_file():
        raise RuntimeError("找不到应用启动文件")
    return [str(executable), str(source)]


# 参数通过 argv 传递，路径和应用名称不拼接到 shell 脚本中。
WAIT_FOR_EXIT = '''
restart_pid="$1"
shift
restart_attempt=0
while kill -0 "$restart_pid" 2>/dev/null; do
    if [ "$restart_attempt" -ge 150 ]; then exit 1; fi
    restart_attempt=$((restart_attempt + 1))
    sleep 0.2
done
exec "$@"
'''


def launch_after_exit(command, parent_pid=None):
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if sys.platform == "win32":
        helper = [sys.executable]
        if not getattr(sys, "frozen", False):
            helper.append(str(Path(__file__).resolve()))
        helper.extend(["--restart-helper", str(parent_pid if parent_pid is not None else os.getpid()),
                       json.dumps(command, ensure_ascii=False)])
        return subprocess.Popen(helper, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, close_fds=True, env=env,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    return subprocess.Popen(
        ["/bin/sh", "-c", WAIT_FOR_EXIT, "mouse-assistant-restart",
         str(parent_pid if parent_pid is not None else os.getpid()), *command],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, env=env,
    )


def run_windows_helper(arguments):
    import ctypes
    if sys.platform != "win32" or len(arguments) != 2:
        return 2
    pid, command = int(arguments[0]), json.loads(arguments[1])
    if pid <= 0 or not isinstance(command, list) or not command or not all(isinstance(v, str) for v in command):
        return 2
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle:
        try:
            if kernel32.WaitForSingleObject(handle, 30000) != 0:
                return 1
        finally:
            kernel32.CloseHandle(handle)
    elif ctypes.get_last_error() != 87:  # 已不存在的 PID；其他错误不能当成已退出。
        return 1
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, env=env,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_windows_helper(sys.argv[2:]) if len(sys.argv) > 1 and sys.argv[1] == "--restart-helper" else 2)
