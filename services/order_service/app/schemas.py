from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OpeningHours(BaseModel):
    open: str | None = None
    close: str | None = None


class RestaurantOut(BaseModel):
    id: int
    name: str
    cuisine: list[str]
    food: list[str]
    opening_hours: OpeningHours
    image_url: str | None = None
    rating: float

    model_config = {'from_attributes': True}


class RestaurantListOut(BaseModel):
    page: int
    limit: int
    items_count: int
    items: list[RestaurantOut]


class FoodOut(BaseModel):
    id: int
    restaurant_id: int
    name: str
    description: str | None = None
    cuisine_type: str
    food_type: str
    price: float
    is_available: bool
    image_url: str | None = None

    model_config = {'from_attributes': True}


class FoodListOut(BaseModel):
    page: int
    limit: int
    items_count: int
    items: list[FoodOut]


class OrderItemIn(BaseModel):
    food_id: int
    quantity: int = Field(gt=0)


class OrderCreateIn(BaseModel):
    items: list[OrderItemIn]
    restaurant_id: int
    payment_method: Literal['online', 'offline']
    delivery_address: str


class OrderCreateOut(BaseModel):
    order_id: int
    status: str
    total_amount: float
    order_time: datetime


class OrderItemOut(BaseModel):
    food_id: int
    food_name: str
    quantity: int
    price_at_time: float

    model_config = {'from_attributes': True}


class OrderOut(BaseModel):
    id: int
    restaurant_id: int
    delivery_address: str
    total_amount: float
    status: str
    payment_method: str
    order_time: datetime
    items: list[OrderItemOut]


class OrderEvent(BaseModel):
    event_type: str
    order_id: int
    restaurant_id: int
    status: str
    payload: dict


class StatusSyncIn(BaseModel):
    order_id: int
    status: str