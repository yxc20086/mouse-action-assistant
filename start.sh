#!/bin/bash
# 启动脚本：自动定位当前目录并调用虚拟环境执行
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 检查虚拟环境
if [ ! -f "venv/bin/python3" ]; then
    echo "正在初始化虚拟环境..."
    python3 -m venv venv
    ./venv/bin/python3 -m pip install -r requirements.txt
fi

echo "正在启动鼠标动作助手..."
./venv/bin/python3 app.py
