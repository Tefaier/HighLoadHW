# Deployment

## 1.1 Описание развертывания

## 1.2 Стратегия деплоя

Деплой в виде комбинации canary и rolling. 
- canary имеет плюс, что можно проверить корректность релиза до того, как он становится доступен всем. Единственное минус, что это поставит требование иметь несколько реплик даже на api сервис, где большой rps не ожидается. Также изоляция не будет полной, потому что новые и старые инстансы будут общаться через бд и брокер сообщений. Тем не менее это позволит по мониторингу понять, если с релизом что-то не так, и купировать потери до выкатки на большее количество реплик.
- rolling не избежен при большом количестве инстансов. Order service будет иметь множество инстансов как в canary, так и обычной части. Чтобы rps живые реплики выдерживали rps нужно будет rolling делать, по 10% инстансов за раз (минимум 1).

Накатывание новой версии конкретного инстанса.
- liveness. Сервисы будут отвечать alive, когда запустился fastapi (способен ответить на ручку). ready будут отвечать когда установилось соединение с бд и очередью (в случае если сервис использует), чтобы гарантировать возможность обрабатывать запросы.
- Для сервиса, чтобы не потерять заказы, важно обеспечивать корректную остановку инстансов. При получении сигнала он останавливает запуск новых cron таск и переводит ready статус в 503. Потом через 3 минут приложение убивается.

Накатывание новой версии схемы бд.
- для всех случаев expand/contract метод обновление. Исключение, если добавляется например новая таблица или то, что не использовалось - тогда expant/contract не нужен.
- для простых действий с метадатой таблиц обновление через обычные скрипты. Если обновление по времени растер пропорционально размеру таблицы, то по возможности через `pg_migrate` или через механизмы postgresql, которые позволяют избежать блокировки (например `create index concurrently` или `not valid`). Нужно будет учитывать необходимое место для работы `pg_migrate` на создание дубликата таблицы, если будет использоваться он.

## 1.3 Observability

### Алерт №1 — Latency (SLI: p99 создания заказа)
- **Метрика**: `http_request_duration_seconds{service="order-service", endpoint="/order", method="POST", quantile="0.99"}`
- **Порог**: `> 500ms`
- **Окно**: `за 5 минут`
- **Задержка**: `5 минут`
- **Сервис**: `order service`
- **Уровень тревоги**: Warning (далее Critical, если >800ms)

### Алерт №2 — Throughput (исчезли запросы)
- **Метрика**: `rate(http_requests_total{service="order-service", endpoint="/order", method="POST", status=~"2.."}[1m])`
- **Порог**: `< 10 RPS`
- **Окно**: `за 3 минуты`
- **Задержка**: `5 минут`
- **Сервис**: `order service`
- **Уровень тревоги**: Critical

### Алерт №3 — Availability (5xx ошибки) (SLO: 99.95%)
- **Метрика**: `rate(http_requests_total{service="order-service", endpoint="/order", method="POST", status=~"5.."}[1m]) / rate(http_requests_total{service="order-service", endpoint="/order", method="POST"}[1m]) * 100`
- **Порог**: `> 0.05%` (99.95% availability)
- **Окно**: `за 2 минуты`
- **Задержка**: `1 минут`
- **Сервис**: `order service`
- **Уровень тревоги**: Critical

### Алерт №4 — Saturation (скопление заказов в статусе pending в БД1, метрику считает cron таска в одном инстансе)
- **Метрика**: `rate(db_order_requests{service="order-service", count(order_status == 'pending')}[1m])`
- **Порог**: `> 100000` (примерно 15 минут необработанных заказов)
- **Окно**: `за 5 минуту`
- **Задержка**: `1 минут`
- **Почему**: Показывает, что tracking service не забирает записи из очереди или их не берут доставщики или не работает обратное обновление через очередь

---

### Уровень 1: Overview Dashboard  
- **Traffic**  
  - RPS по каждому сервису — отдельно чтение / запись  

- **Errors**  
  - % 4xx и 5xx по каждому сервису (order / api / tracking)

- **Latency**  
  - p99 order service (POST /order) 
  - p95 order service (GET /restaurant/list)
  - p95 order service (GET /restaurant/*/food/list)
  - p95 api service (PATCH /restaurant)  
  - p95 tracking service (PATCH /order/{id})  

- **Saturation**  
  - Размер очереди message broker (RabbitMQ)  
  - Количество заказов в БД2 со статусом pending / confirmed  
  - CPU / Memory usage (в среднем по сервисам)
  - количество инстансов каждого сервиса

---

### Уровень 2: Service Dashboard 
#### 2.1 Order Service Dashboard
- **Endpoints**  
  - POST /order — RPS, p99 latency, успех/ошибки (по кодам 2**/4**/5**)  
  - GET /restaurant/list — RPS, p95 latency, errors
  - GET /restaurant/*/food/list — RPS, p95 latency, errors

- **Database (БД1)**  
  - Среднее время выполнения запросов к БД
  - Количество активных транзакций  
  - Количество записей order по разным status 
  - Idempotency key overlap — кол-во вызовов создания заказа с известным ключом

- **Message Broker**  
  - RPS вызовов
  - p95 времени ответа 

#### 2.2 API Service Dashboard
- **Endpoints**  
  - POST /admin/restaurants — RPS, p95 latency, errors  
  - PATCH /admin/restaurants — RPS, p95 latency, errors  
  - POST /admin/foods — RPS, p95 latency, errors  
  - PATCH /admin/foods — RPS, p95 latency, errors  
  - POST /courier — rps создания курьеров

- **S3**
  - общая скорость записи в s3

#### 2.3 Tracking Service Dashboard
- **Endpoints**  
  - GET /orders — RPS, p99 latency
  - PATCH /order/*?status=… — RPS, p99 latency, errors

- **Database (БД2)**
  - Количество заказов по статусам (pending → delivery → finished)  

- **Message Broker**  
  - Max разницы времени между временем создания заказа и временем обработки сообщения о создании заказа

---

### Уровень 3: Diagnostic Dashboard
- **Трейсы**
  - Фильтр по trace_id

- **Логи**  
  - Поиск по trace_id, rid, status, источник (включая nginx)

- **Метрики**  
  - threads, RAM usage, CPU usage в каждом сервисе и инстансе
  - RPS, p99, errors на запросы проведения оплаты

- **Database**
  - Количество ошибок в БД1 и БД2
  - Время WAIT ивентов в БД1 и БД2
  - Свободное место в БД1 и БД2

- **Broker - RabbitMQ**  
  - RabbitMQ: количество неподтвержденных сообщений  
  - Количество упавших нод

- **S3**:
  - Свободное место в S3 bucket

---

### Логи

Json формат логов.

Обязательный поля:
- time (YYYY-MM-DDTHH:mm:ss.sssZ) (UTC+0)
- service_name
- host (service, сервер, номер)
- rid
- message
- level

Необязательные поля:
- trace_id (по возможности всегда)
- meta (все остальное в формате json)

Для nginx:
- host
- upstream
- rid
- status
- request

Логируем (экспортируем) абсолютно все, что залогированно в коде, включая все http запросы (на начало запроса и на ответ). Для библиотек логи ограничены: только логи запросов и ошибок к бд, rabbitmq. Отдельно nginx где логируем на моменте ответа клиенту или завершения соединения (когда клиент оборвал соединение).

## 2 Доступность

## 3 ТСО
