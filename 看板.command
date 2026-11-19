#!/bin/bash
# OpenWrite 故事看板 · 双击启动（macOS）
#
# 启动本地看板服务并自动打开默认浏览器。
# 停止看板：关闭本窗口，或按 Ctrl+C。
# 若提示「复用现有实例」，说明看板已在运行，本窗口可关闭。
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "未找到 .venv/bin/python —— 请先按 docs/setup.md 安装依赖："
    echo "  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
    echo ""
    read -r -p "按回车关闭本窗口…"
    exit 1
fi

exec .venv/bin/python openwrite.py board
