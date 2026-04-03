#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

PORT=5002
PID_FILE="$PWD/.cron-panel.pid"
LOG_FILE="$PWD/server.log"

stop_port() {
  local target_port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${target_port}/tcp" >/dev/null 2>&1 || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -t -iTCP:${target_port} -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "${pids}" ]; then
      kill ${pids} >/dev/null 2>&1 || true
      sleep 1
      kill -9 ${pids} >/dev/null 2>&1 || true
    fi
  fi
}

port_in_use() {
  local target_port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:${target_port} -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltn | grep -q ":${target_port} "
    return $?
  fi
  return 1
}

if [ -f "$PID_FILE" ]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
    kill "$old_pid" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$old_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$PID_FILE"
fi

stop_port 5000
stop_port 5001
stop_port 5002
stop_port 4173

if port_in_use 5002; then
  echo "端口 5002 仍被占用，请先关闭占用进程后再执行。"
  exit 1
fi

echo "📦 Building frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
  npm install
fi
npm run build
cd ..

echo "🚀 Starting backend server on port ${PORT}..."
nohup python3 backend/server.py >"$LOG_FILE" 2>&1 &
new_pid=$!
echo "$new_pid" > "$PID_FILE"
sleep 1

if ! kill -0 "$new_pid" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "启动失败，日志如下："
  tail -n 50 "$LOG_FILE" || true
  exit 1
fi

echo "✅ Linux Cron Panel started at http://localhost:${PORT}"
echo "PID: $new_pid"
