#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo '需要 Node.js 22.12.0 或更新版本，以及 npm。' >&2
  exit 1
fi

if ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1)'; then
  echo "当前 Node.js 版本为 $(node --version)，需要 22.12.0 或更新版本；使用 nvm 时请先运行 nvm use。" >&2
  exit 1
fi

if ! npm ls --depth=0 --silent >/dev/null 2>&1; then
  echo '安装项目依赖…'
  npm ci --include=dev
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo '已创建 .env；如需模型和实时供应商数据，请在其中填写对应密钥。'
fi

echo '网页：http://127.0.0.1:5173'
echo 'API：http://127.0.0.1:4174'
exec npm run dev
