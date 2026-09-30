"""在旧进程退出后重新打开当前应用，不启动其他同名版本。"""
import os
from pathlib import Path
import subprocess
import sys


def restart_command():
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
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
    return subprocess.Popen(
        ["/bin/sh", "-c", WAIT_FOR_EXIT, "mouse-assistant-restart",
         str(parent_pid if parent_pid is not None else os.getpid()), *command],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True, env=env,
    )
