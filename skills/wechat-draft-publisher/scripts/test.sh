#!/bin/bash
# 快速测试脚本：会真实调用微信 API 创建一篇测试草稿

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=== 微信公众号草稿发布工具 - 测试 ==="
echo ""

# 检查项目 openwrite.yaml 中的凭证是否已填写（不打印密钥内容）
if ! python3 - "$PROJECT_ROOT" <<'PY' 2>/dev/null
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
import preferences
preferences.require_wechat_credentials(root)
PY
then
    echo "❌ 微信凭证未配置，请先运行: python3 $PROJECT_ROOT/openwrite.py setup"
    echo "   然后编辑 $PROJECT_ROOT/openwrite.yaml，在 wechat.accounts.<账号名> 下填写 app_id 和 app_secret"
    exit 1
fi

echo "✓ 凭证已配置"
echo ""

# 测试发布示例文章
echo "→ 正在测试发布示例文章..."
echo ""

python3 "$SCRIPT_DIR/../publisher.py" \
    --title "测试文章 - $(date '+%Y-%m-%d %H:%M:%S')" \
    --content "$SCRIPT_DIR/../examples/example.html" \
    --author "测试作者" \
    --digest "这是一篇测试文章"

echo ""
echo "测试完成！请前往公众号后台查看草稿"
