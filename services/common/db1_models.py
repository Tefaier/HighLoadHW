from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class OrderStatus(str, enum.Enum):
    in_payment = 'in_payment'
    created = 'created'
    pending = 'pending'
    confirmed = 'confirmed'
    preparing = 'preparing'
    delivery = 'delivery'
    finished = 'finished'
    cancelled = 'cancelled'


class PaymentMethod(str, enum.Enum):
    online = 'online'
    offline = 'offline'


class User(Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)

    restaurant_admins = relationship('RestaurantAdmin', back_populates='user', cascade='all, delete-orphan')
    orders = relationship('Order', back_populates='user')


class Restaurant(Base):
    __tablename__ = 'restaurant'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cuisine: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    food: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    open_hours_from: Mapped[str | None] = mapped_column(String(5))
    open_hours_to: Mapped[str | None] = mapped_column(String(5))
    image_url: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[float] = mapped_column(Numeric(2, 1), nullable=False, default=0)

    foods = relationship('Food', back_populates='restaurant', cascade='all, delete-orphan')
    admins = relationship('RestaurantAdmin', back_populates='restaurant', cascade='all, delete-orphan')
    orders = relationship('Order', back_populates='restaurant')


class RestaurantAdmin(Base):
    __tablename__ = 'restaurant_admin'

    user_id: Mapped[int] = mapped_column(ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurant.id', ondelete='CASCADE'), primary_key=True)

    user = relationship('User', back_populates='restaurant_admins')
    restaurant = relationship('Restaurant', back_populates='admins')


class Food(Base):
    __tablename__ = 'food'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurant.id', ondelete='CASCADE'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cuisine_type: Mapped[str] = mapped_column(String(50), nullable=False)
    food_type: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)

    restaurant = relationship('Restaurant', back_populates='foods')
    order_items = relationship('OrderItem', back_populates='food')


class Order(Base):
    __tablename__ = 'order'
    __table_args__ = (
        UniqueConstraint('creation_key', name='uq_order_creation_key'),
        CheckConstraint('total_amount >= 0', name='ck_order_total_amount_non_negative'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    creation_key: Mapped[str | None] = mapped_column(UUID(as_uuid=False), unique=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('user.id', ondelete='SET NULL'))
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurant.id', ondelete='RESTRICT'), nullable=False)
    order_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name='order_status_main'), nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod, name='payment_method_main'), nullable=False)

    user = relationship('User', back_populates='orders')
    restaurant = relationship('Restaurant', back_populates='orders')
    items = relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')


class OrderItem(Base):
    __tablename__ = 'order_item'
    __table_args__ = (
        CheckConstraint('quantity > 0', name='ck_order_item_quantity_positive'),
        CheckConstraint('price_at_time >= 0', name='ck_order_item_price_non_negative'),
    )

    order_id: Mapped[int] = mapped_column(ForeignKey('order.id', ondelete='CASCADE'), primary_key=True)
    food_id: Mapped[int] = mapped_column(ForeignKey('food.id', ondelete='RESTRICT'), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price_at_time: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    order = relationship('Order', back_populates='items')
    food = relationship('Food', back_populates='order_items')


class Rating(Base):
    __tablename__ = 'rating'

    user_id: Mapped[int] = mapped_column(ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    restaurant_id: Mapped[int] = mapped_column(ForeignKey('restaurant.id', ondelete='CASCADE'), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
