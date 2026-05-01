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

## Архитектурные паттерны

В MVP использованы как design patterns, так и resilience patterns.

### Design patterns

**Microservices**  
Система разделена на три независимых сервиса: `order-service`, `api-service`, `tracking-service`. Это видно в `docker-compose.yml`, где каждый сервис запускается отдельным контейнером.  
Ссылка: [`docker-compose.yml`](../docker-compose.yml#L58-L131)

**Database per service**  
Для разных частей системы используются отдельные базы данных: основной Postgres для каталога и заказов, отдельный Postgres для трекинга.  
Ссылки: [`docker-compose.yml`](../docker-compose.yml#L1-L39)

**DTO / schema separation**  
Внешние API-формы отделены от ORM-моделей через Pydantic-схемы. Это делает контракт API явным и уменьшает связанность кода.  
Ссылка: [`schemas.py`](../services/order_service/app/schemas.py#L9-L103)

**Event-driven communication**  
Обмен между сервисами завязан на события в RabbitMQ: заказ создаётся в `order-service`, публикуется событие `order.created`, а `tracking-service` его потребляет и создаёт запись у себя.  
Ссылки: [`queue.py`](../services/common/queue.py#L13-L48), [`order_service/main.py`](../services/order_service/app/main.py#L241-L317), [`tracking_service/main.py`](../services/tracking_service/app/main.py#L118-L171)

### Resilience patterns

**Idempotency key**  
Создание заказа через `POST /order` защищено от дублей с помощью `key`: если запрос с тем же ключом повторяется, новый заказ не создаётся.  
Ссылка: [`order_service/main.py`](../services/order_service/app/main.py#L248-L248)

**Async queue processing**  
Тяжёлая связность между сервисами вынесена в очередь RabbitMQ. Это позволяет не блокировать основной сценарий создания заказа и обрабатывать события асинхронно.  
Ссылки: [`queue.py`](../services/common/queue.py#L13-L48), [`order_service/main.py`](../services/order_service/app/main.py#L301-L317), [`tracking_service/main.py`](../services/tracking_service/app/main.py#L118-L156)

**Reconnect / retry on queue consumer**  
Если RabbitMQ или соединение временно недоступны, consumer переподключается в цикле. Это повышает устойчивость к кратковременным сбоям инфраструктуры.  
Ссылки: [`order_service/main.py`](../services/order_service/app/main.py#L327-L352), [`tracking_service/main.py`](../services/tracking_service/app/main.py#L159-L159)

**Health checks**  
У каждого сервиса есть `GET /healthz`, чтобы быстро проверять его готовность и использовать это в smoke-test.  
Ссылки: [`order_service/main.py`](../services/order_service/app/main.py#L127-L129), [`api_service/main.py`](../services/api_service/app/main.py#L38-L40), [`tracking_service/main.py`](../services/tracking_service/app/main.py#L43-L45)


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
## Или то же самое можно сделать через docker, по факту дергаются те же самые ручки
```bash
docker compose ps
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

## Нагрузочные тесты

Для тестирования нагрузки используются три теста - smoke, stress, load

Запуск как на семинаре:

```bash
cd k6
chmod +x run.sh
./run.sh smoke # (или stress, или load)
```

### Для полной проверки работоспособности используется скрипт `smoke.js`.

Он делает следующее:

1. Проверяет список ресторанов и меню
2. Создаёт заказ
3. Проверяет, что заказ попал в tracking-service
4. Проверяет `GET /order/{id}`
5. Меняет статус заказа
6. Проверяет синхронизацию статуса
7. Перезапускает стек и проверяет сохранность данных

### stress.js
максимизирующий сценарий c несколькими ступенями - разогрев и дальше плавное повышение нагрузки вплоть до отказа

### load.js
тест под длительную целевую нагрузку - разогрев и steady нагрузка 15 минут

### Метрики смотреть на http://127.0.0.1:5665/ui/?endpoint=/

## Optimisation iterations
[логи](../docs/optimization-log.md)

### Iteration 0:
-  pool size у базы данных оказался недостаточен, запросы стали уходить в таймаут


### Iteration 1
-  поменяли параметры engine и добавили обработку ошибок -> результаты стали более воспроизводимыми, но bottleneck остался

### НФТ
1) По latency и error rate НФТ выполнены (в рамках 200 max rps)
2) Очевидно, 1800 rps недостижимы на текущем прототипе; требуется пересмотреть архитектуру запросов к базе данных и ее очередь, чтобы победить bottleneck
