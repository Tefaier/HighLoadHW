#!/usr/bin/env bash
set -euo pipefail

BASE_ORDER="http://localhost:8000"
BASE_API="http://localhost:8001"
BASE_TRACKING="http://localhost:8002"

ORDER_KEY="$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"

ORDER_BODY='{
  "restaurant_id": 1,
  "payment_method": "online",
  "delivery_address": "Moscow, Pushkina 1",
  "items": [
    {"food_id": 1, "quantity": 2}
  ]
}'

wait_for() {
  local url="$1"
  local name="$2"
  echo "Waiting for $name..."
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is up"
      return 0
    fi
    sleep 1
  done
  echo "Timeout waiting for $name: $url"
  exit 1
}

json_contains() {
  python3 -c '
import json, sys
payload = json.loads(sys.argv[1])
needle = sys.argv[2]

def contains(obj):
    if isinstance(obj, dict):
        return any(contains(v) for v in obj.values())
    if isinstance(obj, list):
        return any(contains(v) for v in obj)
    return str(obj) == needle

sys.exit(0 if contains(payload) else 1)
' "$1" "$2"
}

tracking_status_for_order() {
  python3 -c '
import json, sys
items = json.loads(sys.argv[1])
order_id = int(sys.argv[2])

for item in items:
    if int(item["id"]) == order_id:
        print(item["status"])
        sys.exit(0)

sys.exit(1)
' "$1" "$2"
}

echo "Bringing stack down/up..."
docker compose down -v
docker compose up --build -d

wait_for "$BASE_ORDER/healthz" "order-service"
wait_for "$BASE_API/healthz" "api-service"
wait_for "$BASE_TRACKING/healthz" "tracking-service"

echo "Checking health endpoints..."
curl -fsS "$BASE_ORDER/healthz"
echo
curl -fsS "$BASE_API/healthz"
echo
curl -fsS "$BASE_TRACKING/healthz"
echo

echo "Checking restaurants and menu..."
RESTAURANTS_JSON="$(curl -fsS "$BASE_ORDER/restaurant/list")"
echo "$RESTAURANTS_JSON"
json_contains "$RESTAURANTS_JSON" "Итальянская пиццерия"
echo "OK: restaurant list contains Итальянская пиццерия"

FOODS_JSON="$(curl -fsS "$BASE_ORDER/restaurant/1/food/list")"
echo "$FOODS_JSON"
json_contains "$FOODS_JSON" "Маргарита"
echo "OK: food list contains Маргарита"

echo "Creating order..."
CREATE_JSON="$(curl -fsS -X POST "$BASE_ORDER/order?key=$ORDER_KEY" \
  -H "Content-Type: application/json" \
  -d "$ORDER_BODY")"
echo "$CREATE_JSON"

ORDER_ID="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["order_id"])' "$CREATE_JSON")"
echo "Order ID: $ORDER_ID"

echo "Waiting for tracking-service to receive order..."
TRACKING_JSON=""
TRACKING_STATUS=""
FOUND="false"

for _ in $(seq 1 30); do
  TRACKING_JSON="$(curl -fsS "$BASE_TRACKING/orders" || true)"
  if [ -n "$TRACKING_JSON" ]; then
    if TRACKING_STATUS="$(tracking_status_for_order "$TRACKING_JSON" "$ORDER_ID" 2>/dev/null)"; then
      FOUND="true"
      break
    fi
  fi
  sleep 1
done

if [ "$FOUND" != "true" ]; then
  echo "FAIL: tracking-service did not receive order $ORDER_ID"
  echo "$TRACKING_JSON"
  exit 1
fi

echo "$TRACKING_JSON"
echo "Tracking status: $TRACKING_STATUS"

echo "Checking GET /order/{id}..."
ORDER_JSON="$(curl -fsS "$BASE_ORDER/order/$ORDER_ID")"
echo "$ORDER_JSON"
json_contains "$ORDER_JSON" "$ORDER_ID"
echo "OK: order detail exists"

case "$TRACKING_STATUS" in
  pending)
    TARGET_STATUS="confirmed"
    ;;
  confirmed)
    TARGET_STATUS="preparing"
    ;;
  preparing)
    TARGET_STATUS="delivery"
    ;;
  delivery)
    TARGET_STATUS="finished"
    ;;
  finished|cancelled)
    TARGET_STATUS="$TRACKING_STATUS"
    ;;
  *)
    echo "Unexpected tracking status: $TRACKING_STATUS"
    exit 1
    ;;
esac

if [ "$TRACKING_STATUS" != "$TARGET_STATUS" ]; then
  echo "Updating status in tracking-service: $TRACKING_STATUS -> $TARGET_STATUS"
  PATCH_JSON="$(curl -fsS -X PATCH "$BASE_TRACKING/order/$ORDER_ID" \
    -H "Content-Type: application/json" \
    -d "{\"status\":\"$TARGET_STATUS\"}")"
  echo "$PATCH_JSON"
  json_contains "$PATCH_JSON" "$TARGET_STATUS"
  echo "OK: tracking-service updated status"
fi

echo "Waiting for order-service to reflect status..."
for _ in $(seq 1 20); do
  ORDER_AFTER_JSON="$(curl -fsS "$BASE_ORDER/order/$ORDER_ID")"
  echo "$ORDER_AFTER_JSON"
  CURRENT_STATUS="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["status"])' "$ORDER_AFTER_JSON")"
  if [ "$CURRENT_STATUS" = "$TARGET_STATUS" ]; then
    echo "OK: order-service reflects status $TARGET_STATUS"
    break
  fi
  sleep 1
done

echo "Restart persistence check..."
docker compose down
docker compose up -d

wait_for "$BASE_ORDER/healthz" "order-service after restart"
wait_for "$BASE_TRACKING/healthz" "tracking-service after restart"

RESTART_ORDER_JSON="$(curl -fsS "$BASE_ORDER/order/$ORDER_ID")"
echo "$RESTART_ORDER_JSON"
json_contains "$RESTART_ORDER_JSON" "$ORDER_ID"
echo "OK: order persisted after restart"

echo "All smoke tests passed."