from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Numeric, String, Text, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class OrderStatus(str, enum.Enum):
    pending = 'pending'
    confirmed = 'confirmed'
    preparing = 'preparing'
    delivery = 'delivery'
    finished = 'finished'
    cancelled = 'cancelled'


class PaymentMethod(str, enum.Enum):
    online = 'online'
    offline = 'offline'


class Courier(Base):
    __tablename__ = 'courier'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(100), nullable=False)


class TrackingOrder(Base):
    __tablename__ = 'order'
    __table_args__ = (
        CheckConstraint('total_amount >= 0', name='ck_tracking_order_total_amount_non_negative'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    courier_id: Mapped[int | None] = mapped_column(ForeignKey('courier.id', ondelete='RESTRICT'))
    order_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name='order_status_tracking'), nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name='payment_method_tracking'), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)

    courier = relationship('Courier')
