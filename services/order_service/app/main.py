from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from decimal import Decimal

import pika

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from services.common.db import Base, make_engine, make_session_factory, wait_for_database
from services.common.db1_models import (
    Food,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    Restaurant,
    User,
)
from services.common.queue import RabbitPublisher
from services.common.settings import settings

from .schemas import (
    FoodListOut,
    OrderCreateIn,
    OrderCreateOut,
    OrderEvent,
    OrderItemOut,
    OrderOut,
    RestaurantListOut,
    RestaurantOut,
    OpeningHours,
    StatusSyncIn,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)
publisher = RabbitPublisher(settings.rabbitmq_url)

app = FastAPI(title='Order Service', version='0.1.0')


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed(db: Session) -> None:
    if db.scalar(select(Restaurant.id).limit(1)) is not None:
        return

    user = User(login='demo', password='demo', phone='+70000000000', address='Moscow')
    r1 = Restaurant(
        name='Итальянская пиццерия',
        cuisine=['Italian', 'Mediterranean'],
        food=['Pizza', 'Tea'],
        open_hours_from='10:00',
        open_hours_to='23:00',
        image_url='https://example.com/photo1.jpg',
        rating=4.5,
    )
    r2 = Restaurant(
        name='Суши-бар',
        cuisine=['Japanese'],
        food=['Sushi', 'Tea'],
        open_hours_from='11:00',
        open_hours_to='22:00',
        image_url='https://example.com/photo2.jpg',
        rating=4.7,
    )
    db.add_all([user, r1, r2])
    db.flush()
    db.add_all([
        Food(
            restaurant_id=r1.id,
            name='Маргарита',
            description='Классика',
            cuisine_type='Italian',
            food_type='Pizza',
            price=Decimal('499.00'),
            is_available=True,
        ),
        Food(
            restaurant_id=r1.id,
            name='Чай',
            description='Чёрный чай',
            cuisine_type='Mediterranean',
            food_type='Tea',
            price=Decimal('99.00'),
            is_available=True,
        ),
        Food(
            restaurant_id=r2.id,
            name='Филадельфия',
            description='Лосось и сыр',
            cuisine_type='Japanese',
            food_type='Sushi',
            price=Decimal('699.00'),
            is_available=True,
        ),
    ])
    db.commit()


@app.on_event('startup')
def startup() -> None:
    wait_for_database(engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _seed(db)
    threading.Thread(target=consume_status_changed, daemon=True).start()


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'service': 'order-service'}


def _parse_query(query: str | None):
    cuisine_filters: list[str] = []
    food_filters: list[str] = []
    if not query:
        return cuisine_filters, food_filters

    for block in query.split(';'):
        if not block.strip() or ':' not in block:
            continue
        key, values = block.split(':', 1)
        values_list = [v.strip().lower() for v in values.split(',') if v.strip()]
        if key.strip() == 'cuisine':
            cuisine_filters.extend(values_list)
        elif key.strip() == 'food':
            food_filters.extend(values_list)
    return cuisine_filters, food_filters


@app.get('/restaurant/list', response_model=RestaurantListOut)
def restaurant_list(
    page: int = Query(1, ge=1),
    query: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    cuisine_filters, food_filters = _parse_query(query)
    restaurants = list(db.scalars(select(Restaurant).order_by(Restaurant.id.asc())).all())

    def match(r: Restaurant) -> bool:
        cuisine_values = [x.lower() for x in r.cuisine or []]
        food_values = [x.lower() for x in r.food or []]
        cuisine_ok = not cuisine_filters or any(c in cuisine_values for c in cuisine_filters)
        food_ok = not food_filters or any(f in food_values for f in food_filters)
        return cuisine_ok and food_ok

    filtered = [r for r in restaurants if match(r)]
    start = (page - 1) * limit
    items = filtered[start:start + limit]
    return RestaurantListOut(
        page=page,
        limit=limit,
        items_count=len(filtered),
        items=[
            RestaurantOut(
                id=r.id,
                name=r.name,
                cuisine=r.cuisine,
                food=r.food,
                opening_hours=OpeningHours(open=r.open_hours_from, close=r.open_hours_to),
                image_url=r.image_url,
                rating=float(r.rating),
            )
            for r in items
        ],
    )


@app.get('/restaurant/{restaurant_id}/food/list', response_model=FoodListOut)
def food_list(
    restaurant_id: int,
    page: int = Query(1, ge=1),
    query: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Food).where(Food.restaurant_id == restaurant_id).order_by(Food.id.asc())
    if query:
        q = query.lower().strip()
        stmt = stmt.where(or_(Food.name.ilike(f'%{q}%'), Food.description.ilike(f'%{q}%')))
    foods = list(db.scalars(stmt).all())
    start = (page - 1) * limit
    items = foods[start:start + limit]
    return FoodListOut(page=page, limit=limit, items_count=len(foods), items=items)


def _body_hash(payload: OrderCreateIn) -> str:
    raw = json.dumps(payload.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _serialize_order(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        restaurant_id=order.restaurant_id,
        delivery_address=order.delivery_address,
        total_amount=float(order.total_amount),
        status=order.status.value,
        payment_method=order.payment_method.value,
        order_time=order.order_time,
        items=[
            OrderItemOut(
                food_id=item.food_id,
                food_name=item.food.name if item.food else '',
                quantity=item.quantity,
                price_at_time=float(item.price_at_time),
            )
            for item in order.items
        ],
    )


@app.get('/order/{order_id}', response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail='order not found')
    return _serialize_order(order)


@app.post('/order', response_model=OrderCreateOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreateIn,
    key: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    try:
        creation_key = str(uuid.UUID(key))
    except Exception:
        raise HTTPException(status_code=400, detail='key must be UUID')

    body_hash = _body_hash(payload)
    existing = db.scalar(select(Order).where(Order.creation_key == creation_key))
    if existing:
        if existing.request_hash and existing.request_hash != body_hash:
            raise HTTPException(status_code=409, detail='key already used for different body')
        return OrderCreateOut(
            order_id=existing.id,
            status=existing.status.value,
            total_amount=float(existing.total_amount),
            order_time=existing.order_time,
        )

    restaurant = db.get(Restaurant, payload.restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail='restaurant not found')

    food_ids = [item.food_id for item in payload.items]
    foods_by_id = {f.id: f for f in db.scalars(select(Food).where(Food.id.in_(food_ids))).all()}
    if len(foods_by_id) != len(payload.items):
        raise HTTPException(status_code=404, detail='one or more food items not found')

    total = Decimal('0.00')
    for item in payload.items:
        food = foods_by_id[item.food_id]
        if food.restaurant_id != restaurant.id:
            raise HTTPException(status_code=400, detail='food belongs to another restaurant')
        if not food.is_available:
            raise HTTPException(status_code=409, detail=f'food {food.id} is unavailable')
        total += Decimal(food.price) * item.quantity

    order = Order(
        creation_key=creation_key,
        request_hash=body_hash,
        restaurant_id=restaurant.id,
        delivery_address=payload.delivery_address,
        total_amount=total,
        status=OrderStatus.in_payment if payload.payment_method == 'online' else OrderStatus.created,
        payment_method=PaymentMethod(payload.payment_method),
    )
    db.add(order)
    db.flush()

    for item in payload.items:
        food = foods_by_id[item.food_id]
        db.add(OrderItem(order_id=order.id, food_id=food.id, quantity=item.quantity, price_at_time=food.price))

    db.commit()
    db.refresh(order)

    event = OrderEvent(
        event_type='order.created',
        order_id=order.id,
        restaurant_id=order.restaurant_id,
        status=order.status.value,
        payload={
            'order_id': order.id,
            'items': [{'food_id': item.food_id, 'quantity': item.quantity} for item in payload.items],
            'total_amount': float(order.total_amount),
            'delivery_address': payload.delivery_address,
            'payment_method': payload.payment_method,
        },
    )
    try:
        publisher.publish('order.created', event.model_dump())
    except Exception as exc:
        logger.warning('Failed to publish order.created for order %s: %s', order.id, exc)

    return OrderCreateOut(
        order_id=order.id,
        status=order.status.value,
        total_amount=float(order.total_amount),
        order_time=order.order_time,
    )


def consume_status_changed() -> None:
    while True:
        try:
            params = pika.URLParameters(settings.rabbitmq_url)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue='order.status_changed', durable=True)

            def callback(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode('utf-8'))
                    with SessionLocal() as db:
                        order = db.get(Order, int(payload['order_id']))
                        if not order:
                            return
                        order.status = OrderStatus(payload['status'])
                        db.commit()
                except Exception as exc:
                    logger.exception('Failed to consume order.status_changed: %s', exc)

            channel.basic_consume(queue='order.status_changed', on_message_callback=callback, auto_ack=True)
            logger.info('order-service consuming order.status_changed')
            channel.start_consuming()
        except Exception as exc:
            logger.warning('status consumer reconnect in 2s: %s', exc)
            time.sleep(2)


@app.post('/internal/order/status-sync')
def sync_order_status(payload: StatusSyncIn, db: Session = Depends(get_db)):
    order = db.get(Order, payload.order_id)
    if not order:
        raise HTTPException(status_code=404, detail='order not found')
    try:
        order.status = OrderStatus(payload.status)
    except Exception:
        raise HTTPException(status_code=400, detail='invalid status')
    db.commit()
    return {'ok': True, 'order_id': order.id, 'status': order.status.value}


@app.get('/')
def root():
    return {'service': 'order-service', 'status': 'running'}