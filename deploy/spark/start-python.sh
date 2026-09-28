#!/usr/bin/env bash
set -euo pipefail

cd /home/Developer/travel-agent

# The application runs on Spark; these providers are sibling containers bound
# to the host loopback. Local development uses SSH-forwarded 1417x ports.
export TRAVEL_OTA_MCP_URL=http://127.0.0.1:4176/mcp
export TRAVEL_12306_MCP_URL=http://127.0.0.1:4177/mcp
export TRAVEL_DIDA_MCP_URL=http://127.0.0.1:4178/mcp
export TRAVEL_DATA_MCP_URL=http://127.0.0.1:4179/mcp
export SPARK_COMFY_URL=http://127.0.0.1:8188
export SPARK_QWEN_COMFY_URL=http://127.0.0.1:8191
export SPARK_H3_WORKFLOW_FILE=workflows/minimax-h3-i2v-api.json
export SPARK_QWEN_IMAGE_WORKFLOW_FILE=workflows/qwen-image-2.1-edit-api.json
export SPARK_MODEL_CONTROL=1
export SPARK_QWEN38_URL=http://127.0.0.1:8192
export SPARK_QWEN38_MODEL=qwen38-27b
export SPARK_QWEN38_STICKY=1

exec .venv/bin/uvicorn pyserver.app:app --host 127.0.0.1 --port 4174
