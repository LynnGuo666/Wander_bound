#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, yaml, PIL' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
if [[ ! -d node_modules ]]; then
  npm ci --include=dev
fi
if [[ ! -f dist/index.html ]]; then
  npm run build
fi
if [[ -f .env ]]; then
  set -a
  source ./.env
  set +a
fi

export SPARK_COMFY_URL="${SPARK_COMFY_URL:-http://127.0.0.1:18188}"
export SPARK_QWEN_COMFY_URL="${SPARK_QWEN_COMFY_URL:-http://127.0.0.1:18191}"
export TRAVEL_OTA_MCP_URL="${TRAVEL_OTA_MCP_URL:-http://127.0.0.1:14176/mcp}"
export TRAVEL_12306_MCP_URL="${TRAVEL_12306_MCP_URL:-http://127.0.0.1:14177/mcp}"
export TRAVEL_DIDA_MCP_URL="${TRAVEL_DIDA_MCP_URL:-http://127.0.0.1:14178/mcp}"
export TRAVEL_DATA_MCP_URL="${TRAVEL_DATA_MCP_URL:-http://127.0.0.1:14179/mcp}"
export SPARK_H3_WORKFLOW_FILE="${SPARK_H3_WORKFLOW_FILE:-workflows/minimax-h3-i2v-api.json}"
export SPARK_QWEN_IMAGE_WORKFLOW_FILE="${SPARK_QWEN_IMAGE_WORKFLOW_FILE:-workflows/qwen-image-2.1-edit-api.json}"

echo "FastAPI + 前端：http://127.0.0.1:${PY_PORT:-4176}"
echo 'Spark 工作流经本机 18188 / 18191 API 隧道调用。'
exec .venv/bin/uvicorn pyserver.app:app --host 127.0.0.1 --port "${PY_PORT:-4176}"
