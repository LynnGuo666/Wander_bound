#!/usr/bin/env bash
set -euo pipefail

local_port="${SPARK_LOCAL_PORT:-4175}"
ssh_key="${SPARK_SSH_KEY:-$HOME/.ssh/id_ed25519}"

if [[ ! "$local_port" =~ ^[0-9]+$ ]] || (( local_port < 1024 || local_port > 65535 )); then
  echo 'SPARK_LOCAL_PORT 需要是 1024–65535 的端口号。' >&2
  exit 1
fi
if [[ ! -f "$ssh_key" ]]; then
  echo "找不到 SSH 私钥：$ssh_key" >&2
  exit 1
fi

echo "Spark 调试页：http://127.0.0.1:${local_port}/ （Ctrl+C 关闭隧道）"
exec ssh -N \
  -i "$ssh_key" \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=3 \
  -p 6082 \
  -L "127.0.0.1:${local_port}:127.0.0.1:4174" \
  Developer@106.13.186.155
