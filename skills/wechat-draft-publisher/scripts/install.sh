#!/bin/bash
# WeChat Draft Publisher 安装脚本
# 凭证保存在项目根目录的 .env（已被 Git 忽略），.env.example 只是占位模板。

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "==================================================="
echo "  微信公众号草稿发布工具 - 安装向导"
echo "==================================================="
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到python3，请先安装Python 3.8+"
    exit 1
fi

echo "✓ Python版本: $(python3 --version)"

# 检查requests库
echo "→ 检查依赖..."
if ! python3 -c "import requests" 2>/dev/null; then
    echo "→ 正在安装项目依赖..."
    python3 -m pip install -r "$PROJECT_ROOT/requirements.txt"
fi

echo "✓ 依赖检查完成"
echo ""

# 生成本地 .env（不覆盖已有文件）
echo "→ 准备本地配置文件..."
python3 "$PROJECT_ROOT/openwrite.py" setup

echo ""
echo "==================================================="
echo "  安装完成！"
echo "==================================================="
echo ""
echo "下一步："
echo "  1. 编辑 $PROJECT_ROOT/.env"
echo "  2. 填写 WeChatAppID 和 WeChatAppSecret（可选 WeChatAuthor）"
echo "     获取方式: 公众平台 → 设置与开发 → 基本配置"
echo "  3. 如提示 IP 不在白名单，请在同一页面添加当前服务器 IP"
echo ""
echo "使用方法（在项目根目录执行）："
echo "  python3 openwrite.py publish articles/<文章目录> --title \"标题\""
echo ""
echo "配置文件位置: $PROJECT_ROOT/.env（权限 600，已被 Git 忽略）"
echo "Token缓存位置: $HOME/.wechat-publisher/token_cache.json"
echo ""
