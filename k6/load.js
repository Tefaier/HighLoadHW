import http from "k6/http";
import { check, fail } from "k6";
import {
  baseUrls,
  defaultHttpParams,
  fetchRestaurantFixture,
  orderPayload,
  uniqueKey,
  parseJsonOrFail,
  assertOk,
} from "./lib/common.js";

const targetRps = Number(__ENV.TARGET_RPS || "800");
const warmupRps = Number(__ENV.WARMUP_RPS || "200");
const warmupDuration = __ENV.WARMUP_DURATION || "2m";
const steadyDuration = __ENV.STEADY_DURATION || "15m";

export const options = {
  discardResponseBodies: false,
  scenarios: {
    warmup: {
      executor: "constant-arrival-rate",
      rate: warmupRps,
      timeUnit: "1s",
      duration: warmupDuration,
      preAllocatedVUs: Number(__ENV.WARMUP_PREALLOCATED_VUS || "50"),
      maxVUs: Number(__ENV.WARMUP_MAX_VUS || "200"),
      exec: "mixedFlow",
      tags: { test_type: "load", stage: "warmup" },
    },
    steady: {
      executor: "constant-arrival-rate",
      rate: targetRps,
      timeUnit: "1s",
      duration: steadyDuration,
      startTime: warmupDuration,
      preAllocatedVUs: Number(__ENV.PREALLOCATED_VUS || "250"),
      maxVUs: Number(__ENV.MAX_VUS || "1500"),
      exec: "mixedFlow",
      tags: { test_type: "load", stage: "steady" },
    },
  },
  thresholds: {
    "http_req_failed{test_type:load}": ["rate<0.01"],
    "http_req_duration{test_type:load,stage:steady}": ["p(99)<500"],
  },
};

export function setup() {
  const { order } = baseUrls();
  const fixture = fetchRestaurantFixture(order);
  return { restaurantId: fixture.restaurantId, foodId: fixture.foodId };
}

function weightedChoice() {
  const r = Math.random();
  if (r < 0.55) return "restaurant_list";
  if (r < 0.95) return "food_list";
  return "create_order";
}

function send(orderBaseUrl, type, restaurantId, foodId) {
  if (type === "restaurant_list") {
    const res = http.get(`${orderBaseUrl}/restaurant/list`, {
      ...defaultHttpParams(),
      tags: { endpoint: "restaurant_list" },
    });
    assertOk(res, "restaurant list");
    return;
  }

  if (type === "food_list") {
    const res = http.get(`${orderBaseUrl}/restaurant/${restaurantId}/food/list`, {
      ...defaultHttpParams(),
      tags: { endpoint: "food_list" },
    });
    assertOk(res, "food list");
    return;
  }

  const res = http.post(
    `${orderBaseUrl}/order?key=${uniqueKey("load")}`,
    orderPayload(restaurantId, foodId),
    {
      ...defaultHttpParams(),
      tags: { endpoint: "create_order" },
    }
  );
  assertOk(res, "create order", [200, 201]);
  const body = parseJsonOrFail(res, "create order");
  if (body?.order_id === undefined && body?.id === undefined) {
    fail(`create order response does not contain order id: ${res.body}`);
  }
}

export function mixedFlow(data) {
  const { order } = baseUrls();
  send(order, weightedChoice(), data.restaurantId, data.foodId);
}
