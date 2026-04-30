"""
Tracking Service - Handles courier operations:
- FT-005: Order status tracking for couriers
- FT-006: Courier interface for getting orders, updating status
- Separate DB for active orders only
"""

import os
import sys
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

sys.path.insert(0,  os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.database import (
    get_tracking_db, get_tracking_engine, init_session_factories,
    Courier, TrackingOrder,
    OrderStatus, PaymentMethod
)

# Initialize DB
tracking_engine = get_tracking_engine(os.getenv("TRACKING_DATABASE_URL", "postgresql://postgres:postgres@tracking_db:5432/tracking_db"))
init_session_factories(None, tracking_engine)

app = FastAPI(title="Tracking Service", version="1.0.0")

# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class CourierCreate(BaseModel):
    restaurant_id: int
    password: str

class CourierOut(BaseModel):
    id: int
    restaurant_id: int
    
    class Config:
        from_attributes = True

class OrderContentItem(BaseModel):
    name: str
    quantity: int

class TrackingOrderIn(BaseModel):
    id: int
    restaurant_id: int
    order_time: datetime
    delivery_address: str
    phone: Optional[str]
    total_amount: float
    status: str
    payment_method: str
    content: List[OrderContentItem]

class TrackingOrderOut(BaseModel):
    id: int
    restaurant_id: int
    courier_id: Optional[int]
    order_time: datetime
    delivery_address: str
    phone: Optional[str]
    total_amount: float
    status: str
    payment_method: str
    content: dict
    
    class Config:
        from_attributes = True

class StatusUpdate(BaseModel):
    status: str

class AssignCourier(BaseModel):
    courier_id: int

# ============================================================================
# COURIER ENDPOINTS (FT-006)
# ============================================================================

@app.post("/couriers", response_model=CourierOut, status_code=status.HTTP_201_CREATED)
def create_courier(courier_in: CourierCreate, db: Session = Depends(get_tracking_db)):
    """Create a new courier."""
    courier = Courier(
        restaurant_id=courier_in.restaurant_id,
        password=courier_in.password
    )
    db.add(courier)
    db.commit()
    db.refresh(courier)
    
    return courier

@app.get("/couriers/{courier_id}/orders", response_model=List[TrackingOrderOut])
def get_courier_orders(
    courier_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_tracking_db)
):
    """
    FT-006: Get orders assigned to a courier.
    """
    query = db.query(TrackingOrder).filter(TrackingOrder.courier_id == courier_id)
    
    if status:
        query = query.filter(TrackingOrder.status == status)
    
    orders = query.order_by(TrackingOrder.order_time.desc()).all()
    return orders

# ============================================================================
# ORDER MANAGEMENT (FT-005, FT-006)
# ============================================================================

@app.post("/orders", response_model=TrackingOrderOut, status_code=status.HTTP_201_CREATED)
def create_tracking_order(order_in: TrackingOrderIn, db: Session = Depends(get_tracking_db)):
    """
    Create order in tracking DB (called via broker message from order_service).
    This is the eventual consistency sync point.
    """
    # Check if order already exists
    existing = db.query(TrackingOrder).filter(TrackingOrder.id == order_in.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Order already exists in tracking")
    
    try:
        order_status = OrderStatus(order_in.status)
        payment_method = PaymentMethod(order_in.payment_method)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")
    
    order = TrackingOrder(
        id=order_in.id,
        restaurant_id=order_in.restaurant_id,
        order_time=order_in.order_time,
        delivery_address=order_in.delivery_address,
        phone=order_in.phone,
        total_amount=Decimal(str(order_in.total_amount)),
        status=order_status,
        payment_method=payment_method,
        content={"items": [item.model_dump() for item in order_in.content]}
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    
    return order

@app.get("/orders/{order_id}", response_model=TrackingOrderOut)
def get_order(order_id: int, db: Session = Depends(get_tracking_db)):
    """
    FT-005: Get order status (for both users and couriers).
    """
    order = db.query(TrackingOrder).filter(TrackingOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order

@app.patch("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    update: StatusUpdate,
    db: Session = Depends(get_tracking_db)
):
    """
    FT-006: Update order status (courier action).
    """
    order = db.query(TrackingOrder).filter(TrackingOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    try:
        new_status = OrderStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    order.status = new_status
    db.commit()
    
    return {
        "order_id": order_id,
        "new_status": new_status.value
    }

@app.post("/orders/{order_id}/assign")
def assign_courier(
    order_id: int,
    assign: AssignCourier,
    db: Session = Depends(get_tracking_db)
):
    """
    FT-006: Assign courier to an order.
    """
    order = db.query(TrackingOrder).filter(TrackingOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    courier = db.query(Courier).filter(Courier.id == assign.courier_id).first()
    if not courier:
        raise HTTPException(status_code=404, detail="Courier not found")
    
    order.courier_id = courier.id
    order.status = OrderStatus.Confirmed
    db.commit()
    
    return {
        "order_id": order_id,
        "courier_id": courier.id,
        "status": OrderStatus.Confirmed.value
    }

@app.get("/restaurants/{restaurant_id}/orders", response_model=List[TrackingOrderOut])
def get_restaurant_orders(
    restaurant_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_tracking_db)
):
    """
    Get orders for a restaurant (for courier pickup).
    """
    query = db.query(TrackingOrder).filter(TrackingOrder.restaurant_id == restaurant_id)
    
    if status:
        query = query.filter(TrackingOrder.status == status)
    else:
        # Default: show pending and confirmed orders
        query = query.filter(TrackingOrder.status.in_([
            OrderStatus.Pending, OrderStatus.Confirmed, OrderStatus.Preparing
        ]))
    
    orders = query.order_by(TrackingOrder.order_time).all()
    return orders

# ============================================================================
# BROKER CONSUMER ENDPOINT (simulated)
# ============================================================================

@app.post("/internal/sync-order")
def sync_order_from_broker(data: dict, db: Session = Depends(get_tracking_db)):
    """
    Internal endpoint for broker consumer to sync orders from order_service.
    In production, this would be consumed by a background Kafka consumer.
    """
    order_id = data.get("order_id")
    restaurant_id = data.get("restaurant_id")
    order_status = data.get("status")
    
    existing = db.query(TrackingOrder).filter(TrackingOrder.id == order_id).first()
    if existing:
        # Update status if changed
        if existing.status.value != order_status:
            existing.status = OrderStatus(order_status)
            db.commit()
        return {"action": "updated", "order_id": order_id}
    
    # Create new tracking order (minimal data, full data comes later or via separate call)
    order = TrackingOrder(
        id=order_id,
        restaurant_id=restaurant_id,
        order_time=datetime.utcnow(),
        delivery_address="TBD",
        total_amount=Decimal("0"),
        status=OrderStatus(order_status),
        payment_method=PaymentMethod.Online,
        content={}
    )
    db.add(order)
    db.commit()
    
    return {"action": "created", "order_id": order_id}

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "tracking_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
