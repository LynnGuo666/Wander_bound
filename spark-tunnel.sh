#!/usr/bin/env bash
set -euo pipefail

ssh_key="${SPARK_SSH_KEY:-$HOME/.ssh/id_ed25519}"
local_port="${SPARK_LOCAL_PORT:-4175}"

if [[ ! -f "$ssh_key" ]]; then
  echo "找不到 SSH 私钥：$ssh_key" >&2
  exit 1
fi

if [[ ! "$local_port" =~ ^[0-9]+$ ]] || (( local_port < 1024 || local_port > 65535 )); then
  echo "SPARK_LOCAL_PORT 必须是 1024–65535 之间的端口" >&2
  exit 1
fi

echo "Spark 隧道：网页/API http://127.0.0.1:${local_port}/、OTA 14176、12306 14177、道旅 14178、聚合数据 14179、视觉模型 18192（Ctrl+C 关闭）"
exec ssh -N \
  -i "$ssh_key" \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=3 \
  -p 6082 \
  -L "127.0.0.1:${local_port}:127.0.0.1:4174" \
  -L 127.0.0.1:14176:127.0.0.1:4176 \
  -L 127.0.0.1:14177:127.0.0.1:4177 \
  -L 127.0.0.1:14178:127.0.0.1:4178 \
  -L 127.0.0.1:14179:127.0.0.1:4179 \
  -L 127.0.0.1:18192:127.0.0.1:8192 \
  Developer@106.13.186.155
