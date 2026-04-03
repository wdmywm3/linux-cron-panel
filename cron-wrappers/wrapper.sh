#!/bin/bash
# Linux Cron Panel - Wrapper Script
# 由后端自动调用，用户无需手动使用

TASK_ID="${1:-}"
PANEL_URL="http://127.0.0.1:5002"
shift

if [ -z "$TASK_ID" ]; then
    echo "Usage: $0 <TASK_ID> <command> [args...]"
    exit 1
fi

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 <TASK_ID> <command> [args...]"
    exit 1
fi

LOG_DIR="${HOME}/.openclaw/linux-cron-panel/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/${TASK_ID}.log"

# Execute the actual command
"$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

# Report result to Panel
STATUS="success"
[ $EXIT_CODE -ne 0 ] && STATUS="failure"

curl -sS -X POST "${PANEL_URL}/api/report-run" \
    -H 'Content-Type: application/json' \
    -d "{\"task_id\":\"${TASK_ID}\",\"status\":\"${STATUS}\",\"exit_code\":${EXIT_CODE}}" > /dev/null 2>&1

exit $EXIT_CODE
