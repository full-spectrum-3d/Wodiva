#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$ROOT/backend"
if ! pgrep -f "uvicorn app.core.main:app" > /dev/null; then
  setsid nohup bash -c 'while true; do uvicorn app.core.main:app --host 127.0.0.1 --port 8000; sleep 2; done' >> var/backend.log 2>&1 < /dev/null &
fi

if command -v ollama > /dev/null && ! pgrep -f "ollama serve" > /dev/null; then
  setsid nohup ollama serve > /tmp/ollama.log 2>&1 < /dev/null &
fi

cd "$ROOT/frontend"
[ -d node_modules ] || npm ci --no-audit --no-fund
if ! pgrep -f "ng serve" > /dev/null; then
  setsid nohup bash -c 'while true; do npx ng serve --host 0.0.0.0 --port 4200 --allowed-hosts .app.github.dev; sleep 2; done' >> /tmp/frontend.log 2>&1 < /dev/null &
fi

echo "Wodiva: https://${CODESPACE_NAME:-localhost}-4200.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}/"
