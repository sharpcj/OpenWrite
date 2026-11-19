@echo off
chcp 65001 >nul
rem OpenWrite 故事看板 · 双击启动（Windows）
rem 启动本地看板服务并自动打开默认浏览器。
rem 停止看板：关闭本窗口，或按 Ctrl+C。
rem 若提示「复用现有实例」，说明看板已在运行，本窗口可关闭。
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo 未找到 .venv\Scripts\python.exe —— 请先按 docs\setup.md 安装依赖：
    echo   py -3 -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

.venv\Scripts\python.exe openwrite.py board
