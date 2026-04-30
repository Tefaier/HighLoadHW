# HighLoad MVP
Минимальный рабочий MVP для highload-дз: три микросервиса, две PostgreSQL-базы и RabbitMQ.

## Что реализовано

Система состоит из трёх сервисов:

- **order-service** — список ресторанов, меню, создание заказа, получение заказа по id, синхронизация статуса заказа
- **api-service** — сервис с данными ресторанов и блюд
- **tracking-service** — трекинг заказов и смена статуса доставки

Инфраструктура:

- **PostgreSQL main** — основная база для ресторанов, блюд и заказов
- **PostgreSQL tracking** — отдельная база для tracking-service
- **RabbitMQ** — очередь для передачи событий между сервисами

## Основной сценарий

1. Клиент получает список ресторанов и меню.
2. Клиент создаёт заказ через `order-service`.
3. `order-service` публикует событие в RabbitMQ.
4. `tracking-service` получает заказ и сохраняет его у себя.
5. Статус заказа меняется через `tracking-service`.
6. `order-service` получает обновление статуса и синхронизирует его у себя.

## Технологии

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL 16
- RabbitMQ
- Docker / Docker Compose

## Как запустить

Из корня проекта:

```bash
docker compose up --build
````

После запуска сервисы будут доступны по адресам:

* `order-service` — `http://localhost:8000`
* `api-service` — `http://localhost:8001`
* `tracking-service` — `http://localhost:8002`

## Проверка здоровья сервисов

```bash
curl http://localhost:8000/healthz
curl http://localhost:8001/healthz
curl http://localhost:8002/healthz
```

## Полезные ручки

### order-service

* `GET /restaurant/list`
* `GET /restaurant/{restaurant_id}/food/list`
* `GET /order/{order_id}`
* `POST /order?key=<uuid>`
* `POST /internal/order/status-sync`
* `GET /healthz`

### tracking-service

* `GET /orders`
* `PATCH /order/{order_id}`
* `GET /healthz`

### api-service

* `GET /healthz`

## Пример создания заказа

```bash
curl -X POST "http://localhost:8000/order?key=550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "restaurant_id": 1,
    "payment_method": "online",
    "delivery_address": "Moscow, Pushkina 1",
    "items": [
      {"food_id": 1, "quantity": 2}
    ]
  }'
```

## Проверка tracking-service

```bash
curl http://localhost:8002/orders
```

## Смена статуса заказа

```bash
curl -X PATCH "http://localhost:8002/order/1" \
  -H "Content-Type: application/json" \
  -d '{"status":"confirmed"}'
```

## Smoke test

Для полной проверки работоспособности используется скрипт `smoke_test.sh`.

Он делает следующее:

1. Останавливает контейнеры
2. Удаляет volumes
3. Собирает и запускает стек заново
4. Проверяет health-check'и
5. Проверяет список ресторанов и меню
6. Создаёт заказ
7. Проверяет, что заказ попал в tracking-service
8. Проверяет `GET /order/{id}`
9. Меняет статус заказа
10. Проверяет синхронизацию статуса
11. Перезапускает стек и проверяет сохранность данных

Запуск:

```bash
chmod +x smoke_test.sh
./smoke_test.sh
```

## Smoke test с полного сброса

Если нужно вручную очистить данные перед запуском:

```bash
docker compose down -v
./smoke_test.sh
```

## Статус проекта

Это рабочий MVP. Базовый пользовательский сценарий уже реализован и проходит smoke test.

```

Если хочешь, я могу следующим сообщением сразу сделать тебе ещё и **короткую версию README на английском** или **адаптировать этот README под именно твою структуру папок и имена сервисов**.
```
