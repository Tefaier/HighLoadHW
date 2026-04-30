from __future__ import annotations

import json
import logging
import threading
import time

import pika
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.common.db import Base, make_engine, make_session_factory, wait_for_database
from services.common.db2_models import Courier, OrderStatus, PaymentMethod, TrackingOrder
from services.common.settings import settings

from .schemas import CourierCreateIn, CourierOut, OrderStatusPatchIn, TrackingOrderOut

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)

app = FastAPI(title='Tracking Service', version='0.1.0')


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event('startup')
def startup() -> None:
    wait_for_database(engine)
    Base.metadata.create_all(bind=engine)
    threading.Thread(target=consume_order_created, daemon=True).start()


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'service': 'tracking-service'}


@app.post('/couriers', status_code=status.HTTP_201_CREATED)
def create_courier(payload: CourierCreateIn, db: Session = Depends(get_db)):
    courier = Courier(restaurant_id=payload.restaurant_id, password=payload.password)
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return CourierOut(id=courier.id, restaurant_id=courier.restaurant_id)


@app.get('/couriers/{courier_id}')
def get_courier(courier_id: int, db: Session = Depends(get_db)):
    courier = db.get(Courier, courier_id)
    if not courier:
        raise HTTPException(status_code=404, detail='courier not found')
    return CourierOut(id=courier.id, restaurant_id=courier.restaurant_id)


@app.get('/orders')
def list_orders(status_filter: str | None = Query(None), db: Session = Depends(get_db)):
    stmt = select(TrackingOrder).order_by(TrackingOrder.id.asc())
    if status_filter:
        stmt = stmt.where(TrackingOrder.status == OrderStatus(status_filter))
    items = db.scalars(stmt).all()
    return [
        TrackingOrderOut(
            id=o.id,
            restaurant_id=o.restaurant_id,
            courier_id=o.courier_id,
            status=o.status.value,
            total_amount=float(o.total_amount),
            payment_method=o.payment_method.value,
            content=o.content,
        )
        for o in items
    ]


@app.patch('/order/{order_id}')
def update_order_status(order_id: int, payload: OrderStatusPatchIn, db: Session = Depends(get_db)):
    order = db.get(TrackingOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail='order not found')

    try:
        new_status = OrderStatus(payload.status)
    except Exception:
        raise HTTPException(status_code=400, detail='invalid status')

    valid = {
        OrderStatus.pending: {OrderStatus.confirmed, OrderStatus.cancelled},
        OrderStatus.confirmed: {OrderStatus.preparing, OrderStatus.cancelled},
        OrderStatus.preparing: {OrderStatus.delivery, OrderStatus.cancelled},
        OrderStatus.delivery: {OrderStatus.finished, OrderStatus.cancelled},
        OrderStatus.finished: set(),
        OrderStatus.cancelled: set(),
    }
    if new_status not in valid.get(order.status, set()):
        raise HTTPException(status_code=409, detail='invalid transition')

    order.status = new_status
    db.commit()

    try:
        publish_status_changed(order.id, order.status.value)
    except Exception as exc:  # pragma: no cover
        logger.warning('status_changed publish failed: %s', exc)

    return {'order_id': order.id, 'status': order.status.value}


def consume_order_created() -> None:
    while True:
        try:
            params = pika.URLParameters(settings.rabbitmq_url)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue='order.created', durable=True)

            def callback(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode('utf-8'))
                    order_id = int(payload['order_id'])
                    with SessionLocal() as db:
                        existing = db.get(TrackingOrder, order_id)
                        if existing:
                            return
                        db.add(
                            TrackingOrder(
                                id=order_id,
                                restaurant_id=int(payload['restaurant_id']),
                                courier_id=None,
                                delivery_address=payload['payload'].get('delivery_address', ''),
                                phone=None,
                                total_amount=payload['payload']['total_amount'],
                                status=OrderStatus.pending,
                                payment_method=PaymentMethod.online if payload['payload'].get('payment_method') == 'online' else PaymentMethod.offline,
                                content=payload['payload'],
                            )
                        )
                        db.commit()
                except Exception as exc:
                    logger.exception('Failed to consume order.created: %s', exc)

            channel.basic_consume(queue='order.created', on_message_callback=callback, auto_ack=True)
            logger.info('tracking-service consuming order.created')
            channel.start_consuming()
        except Exception as exc:
            logger.warning('consumer reconnect in 2s: %s', exc)
            time.sleep(2)


def publish_status_changed(order_id: int, status_value: str) -> None:
    params = pika.URLParameters(settings.rabbitmq_url)
    connection = pika.BlockingConnection(params)
    try:
        channel = connection.channel()
        channel.queue_declare(queue='order.status_changed', durable=True)
        channel.basic_publish(
            exchange='',
            routing_key='order.status_changed',
            body=json.dumps({'order_id': order_id, 'status': status_value}).encode('utf-8'),
        )
    finally:
        connection.close()


@app.get('/')
def root():
    return {'service': 'tracking-service', 'status': 'running'}
