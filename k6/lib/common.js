import { check, fail, sleep } from "k6";
import http from "k6/http";
import { randomBytes } from "k6/crypto";

export function env(name, fallback) {
  const value = __ENV[name];
  return value && value.length > 0 ? value : fallback;
}

export function baseUrls() {
  return {
    order: env("BASE_ORDER", "http://localhost:8000"),
    api: env("BASE_API", "http://localhost:8001"),
    tracking: env("BASE_TRACKING", "http://localhost:8002"),
  };
}

export function defaultHttpParams() {
  return {
    headers: { "Content-Type": "application/json" },
    timeout: env("HTTP_TIMEOUT", "10s"),
  };
}

export function assertOk(response, label, expectedStatuses = [200]) {
  const ok = check(response, {
    [`${label} status in ${expectedStatuses.join(", ")}`]: (r) =>
      expectedStatuses.includes(r.status),
  });
  if (!ok) fail(`${label} failed: status=${response.status}, body=${response.body}`);
}

export function parseJsonOrFail(response, label) {
  try {
    return response.json();
  } catch (error) {
    fail(`${label}: invalid JSON (${error.message})`);
  }
}

export function assertContainsText(payload, needle, label) {
  const body = typeof payload === "string" ? payload : JSON.stringify(payload);
  if (!body.includes(String(needle))) {
    fail(`${label}: expected to contain "${needle}"`);
  }
}

export function uniqueKey() {
  const bytes = new Uint8Array(randomBytes(16));

  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
    .slice(6, 8)
    .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
}

export function findOrderStatus(items, orderId) {
  if (!Array.isArray(items)) return null;
  for (const item of items) {
    if (String(item?.id) === String(orderId)) return item?.status ?? null;
  }
  return null;
}

export function waitFor(predicate, { timeoutSeconds = 30, intervalSeconds = 1, label = "condition" } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutSeconds * 1000) {
    const result = predicate();
    if (result) return result;
    sleep(intervalSeconds);
  }
  fail(`Timeout waiting for ${label}`);
}

export function orderPayload(restaurantId, foodId) {
  return JSON.stringify({
    restaurant_id: Number(restaurantId),
    payment_method: "online",
    delivery_address: env("DELIVERY_ADDRESS", "Moscow, Pushkina 1"),
    items: [{ food_id: Number(foodId), quantity: Number(env("ORDER_QUANTITY", "2")) }],
  });
}

export function fetchRestaurantFixture(orderBaseUrl) {
  const restaurantsRes = http.get(`${orderBaseUrl}/restaurant/list`, defaultHttpParams());
  assertOk(restaurantsRes, "restaurant list");
  const restaurants = parseJsonOrFail(restaurantsRes, "restaurant list");

  if (restaurants.length === 0) {
    fail("Restaurant list is empty");
  }

  const restaurantId = restaurants[0]?.id ?? restaurants[0]?.restaurant_id ?? 1;

  const menuRes = http.get(`${orderBaseUrl}/restaurant/${restaurantId}/food/list`, defaultHttpParams());
  assertOk(menuRes, "menu list");
  const menu = parseJsonOrFail(menuRes, "menu list");

  if (menu.length === 0) {
    fail(`Menu for restaurant ${restaurantId} is empty`);
  }

  const foodId = menu[0]?.id ?? menu[0]?.food_id ?? 1;
  return { restaurantId, foodId, restaurants, menu };
}
