import http from "k6/http";
import { fail } from "k6";
import {
  baseUrls,
  defaultHttpParams,
  fetchRestaurantFixture,
  orderPayload,
  uniqueKey,
  parseJsonOrFail,
  assertOk,
} from "./lib/common.js";

const startRate = Number(__ENV.START_RPS || "300");

export const options = {
  discardResponseBodies: false,
  scenarios: {
    stress: {
      executor: "ramping-arrival-rate",
      startRate,
      timeUnit: "1s",
      // __ENV.PREALLOCATED_VUS ||
      preAllocatedVUs: Number("40"),
      // __ENV.MAX_VUS ||
      maxVUs: Number("300"),
      // __ENV.STAGE_1_RPS || 
      stages: [
        { target: Number("10"), duration: "1m" },
        { target: Number("30"), duration: "1m" },
        { target: Number("50"), duration: __ENV.STAGE_1_DURATION || "1m" },
        { target: Number("70"), duration: __ENV.STAGE_2_DURATION || "1m" },
        // { target: Number("90"), duration: __ENV.STAGE_3_DURATION || "1m" },
        // { target: Number("110"), duration: __ENV.STAGE_4_DURATION || "1m" },
        // { target: Number("130"), duration: __ENV.STAGE_5_DURATION || "1m" },
        // { target: Number("150"), duration: __ENV.STAGE_6_DURATION || "1m" },
        { target: Number("200"), duration: __ENV.STAGE_5_DURATION || "1m" },
        { target: Number("300"), duration: __ENV.STAGE_6_DURATION || "1m" },
        { target: Number("500"), duration: __ENV.STAGE_6_DURATION || "1m" },
      ],
      exec: "mixedFlow",
      tags: { test_type: "stress" },
    },
  },
  thresholds: {
    "http_req_failed{test_type:stress}": ["rate<0.05"],
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
    `${orderBaseUrl}/order?key=${uniqueKey("stress")}`,
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
