#!/usr/bin/env bash
set -euo pipefail

SMOKE="${1:-smoke}"
STRESS="${1:-stress}"
LOAD="${1:-load}"
SCRIPT="${STRESS}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="k6/full_reports/${SCRIPT}_${TIMESTAMP}"

mkdir -p "$OUT_DIR"

echo "Starting test: $SCRIPT"
echo "Output dir: $OUT_DIR"

# --- файлы логов ---

K6_REPORT="$OUT_DIR/k6_report.html"
DOCKER_STATS_LOG="$OUT_DIR/docker_stats.log"
IOSTAT_LOG="$OUT_DIR/iostat.log"
PIDSTAT_LOG="$OUT_DIR/pidstat.log"

# --- cleanup handler ---

cleanup() {
echo "Stopping background monitors..."
kill $DOCKER_PID $IOSTAT_PID $PIDSTAT_PID 2>/dev/null || true
}
trap cleanup EXIT

# --- docker stats ---

echo "Starting docker stats..."
docker stats --no-stream=false 
--format "{{.Name}};{{.CPUPerc}};{{.MemUsage}};{{.NetIO}};{{.BlockIO}}" \

> "$DOCKER_STATS_LOG" &
> DOCKER_PID=$!

# --- iostat ---

echo "Starting iostat..."
iostat -xz 1 > "$IOSTAT_LOG" &
IOSTAT_PID=$!

# --- pidstat (CPU + RAM per process) ---

echo "Starting pidstat..."
pidstat -durh 1 > "$PIDSTAT_LOG" &
PIDSTAT_PID=$!

# --- небольшой прогрев перед запуском ---

sleep 2

# --- запуск k6 ---

echo "Starting k6..."
K6_WEB_DASHBOARD=true 
K6_WEB_DASHBOARD_EXPORT="$K6_REPORT" 
k6 run "${SCRIPT}.js"

echo ""
echo "Test finished"
echo "Reports saved in: $OUT_DIR"
