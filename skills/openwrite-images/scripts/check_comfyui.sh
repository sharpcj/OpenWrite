#!/usr/bin/env bash
# Check whether ComfyUI is reachable.
#
# Exit codes:
#   0  ComfyUI is online (HTTP 200 from the root path)
#   1  ComfyUI did NOT respond (offline, unreachable, or timeout)
#
# Configuration:
#   COMFYUI_SERVER_URL – address to probe; may be comma-separated, local first.
#                        Falls back to openwrite.yaml image_sources, then legacy
#                        COMFYUI_URL, then http://localhost:8188.
#
# Usage:
#   bash scripts/check_comfyui.sh
#   COMFYUI_SERVER_URL=http://192.168.1.10:6677 bash scripts/check_comfyui.sh

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${COMFYUI_SERVER_URL:-}" ]]; then
  COMFYUI_SERVER_URL="$(python3 - "$SCRIPT_DIR" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location('image_config', sys.argv[1] + '/image_config.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(','.join(module.comfyui_urls()))
PY
)" || COMFYUI_SERVER_URL="${COMFYUI_URL:-http://localhost:8188}"
fi

# 逗号分隔多地址时逐个探测（配置解析已保证本地地址在前）。
IFS=',' read -ra URLS <<< "$COMFYUI_SERVER_URL"
for URL in "${URLS[@]}"; do
  URL="$(echo "$URL" | xargs)"
  [[ -z "$URL" ]] && continue
  code="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "${URL}/" || true)"
  if [[ "${code}" == "200" ]]; then
    echo "ComfyUI ONLINE  (${URL}, HTTP ${code})"
    exit 0
  fi
  echo "ComfyUI OFFLINE (${URL}, HTTP ${code:-no-response})" >&2
done

echo "  - Start ComfyUI locally and retry, OR" >&2
echo "  - Configure another image source in openwrite.yaml image_sources (fal / hunyuan / stock keys)." >&2
exit 1
