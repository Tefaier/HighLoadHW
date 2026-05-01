from __future__ import annotations

from pydantic import BaseModel


class OrderStatusPatchIn(BaseModel):
    status: str


class CourierCreateIn(BaseModel):
    restaurant_id: int
    password: str


class CourierOut(BaseModel):
    id: int
    restaurant_id: int


class TrackingOrderOut(BaseModel):
    id: int
    restaurant_id: int
    courier_id: int | None
    status: str
    total_amount: float
    payment_method: str
    content: dict
