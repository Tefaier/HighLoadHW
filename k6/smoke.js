import http from "k6/http";
import { check, group, fail } from "k6";
import {
  baseUrls,
  defaultHttpParams,
  assertOk,
  assertContainsText,
  parseJsonOrFail,
  uniqueKey,
  waitFor,
  findOrderStatus,
  orderPayload,
} from "./lib/common.js";

export const options = {
  scenarios: {
    smoke: {
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 1,
      maxDuration: "10m",
    },
  },
  thresholds: {
    http_req_failed: ["rate==0"],
    http_req_duration: ["p(99)<3000"],
  },
};

function createOrder(orderBaseUrl, restaurantId, foodId) {
  const res = http.post(
    `${orderBaseUrl}/order?key=${uniqueKey("smoke")}`,
    orderPayload(restaurantId, foodId),
    defaultHttpParams()
  );
  assertOk(res, "create order", [200, 201]);
  const body = parseJsonOrFail(res, "create order");
  const orderId = body?.order_id ?? body?.id;
  if (orderId === undefined || orderId === null) fail(`No order id in response: ${res.body}`);
  return orderId;
}

function trackingOrders(trackingBaseUrl) {
  const res = http.get(`${trackingBaseUrl}/orders`, defaultHttpParams());
  assertOk(res, "tracking orders");
  return parseJsonOrFail(res, "tracking orders");
}

export default function () {
  const { order, api, tracking } = baseUrls();

  group("health", () => {
    assertOk(http.get(`${order}/healthz`), "order health");
    assertOk(http.get(`${api}/healthz`), "api health");
    assertOk(http.get(`${tracking}/healthz`), "tracking health");
  });

  group("catalog", () => {
    const restaurants = parseJsonOrFail(http.get(`${order}/restaurant/list`, defaultHttpParams()), "restaurant list");
    assertContainsText(restaurants, "Итальянская пиццерия", "restaurant list");

    const menu = parseJsonOrFail(http.get(`${order}/restaurant/1/food/list`, defaultHttpParams()), "food list");
    assertContainsText(menu, "Маргарита", "food list");
  });

  const orderId = createOrder(order, 1, 1);

  group("tracking sync", () => {
    const found = waitFor(() => {
      const items = trackingOrders(tracking);
      const status = findOrderStatus(items, orderId);
      return status ? { items, status } : null;
    }, { timeoutSeconds: 30, intervalSeconds: 1, label: `tracking order ${orderId}` });

    check(found.items, {
      "tracking contains order": (items) => findOrderStatus(items, orderId) !== null,
    });
  });

  group("status propagation", () => {
    const items = trackingOrders(tracking);
    const initial = findOrderStatus(items, orderId);
    if (!initial) fail("Order not found in tracking-service");

    let target = initial;
    switch (initial) {
      case "pending": target = "confirmed"; break;
      case "confirmed": target = "preparing"; break;
      case "preparing": target = "delivery"; break;
      case "delivery": target = "finished"; break;
      case "finished":
      case "cancelled":
        target = initial;
        break;
      default:
        fail(`Unexpected status: ${initial}`);
    }

    if (target !== initial) {
      const patchRes = http.patch(
        `${tracking}/order/${orderId}`,
        JSON.stringify({ status: target }),
        defaultHttpParams()
      );
      assertOk(patchRes, "patch tracking status");
      assertContainsText(parseJsonOrFail(patchRes, "patch tracking status"), target, "patch tracking status");
    }

    const reflected = waitFor(() => {
      const res = http.get(`${order}/order/${orderId}`, defaultHttpParams());
      assertOk(res, "get order");
      const body = parseJsonOrFail(res, "get order");
      return String(body?.status) === String(target) ? body : null;
    }, { timeoutSeconds: 20, intervalSeconds: 1, label: `order ${orderId} status ${target}` });

    check(reflected, {
      "order-service reflects status": (body) => String(body?.status) === String(target),
    });
  });
}
