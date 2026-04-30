#!/usr/bin/env bash
set -euo pipefail

TEST="${1:-smoke}"
SCRIPT="${TEST}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT="./reports/${SCRIPT}_${TIMESTAMP}.json"

mkdir -p ./reports

if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 is not installed or not available in PATH"
  exit 1
fi

K6_WEB_DASHBOARD=true \
K6_WEB_DASHBOARD_EXPORT="$REPORT" \
k6 run --summary-export="$REPORT" "./${SCRIPT}.js"
# pkill k6 || true

echo
echo "Отчёт сохранён: $REPORT"
