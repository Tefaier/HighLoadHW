"""
API Service - Handles user-facing operations:
- FT-001: Browse restaurants with filters
- FT-002: View restaurant menus
- FT-005: View order status
"""

import os
import sys
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

sys.path.insert(0,os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..')))

from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.database import (
    get_main_db, get_main_engine, init_session_factories,
    User, Restaurant, Food, Order
)
# Initialize DB on startup
main_engine = get_main_engine(os.getenv("MAIN_DATABASE_URL", "postgresql://postgres:postgres@main_db:5432/main_db"))
init_session_factories(main_engine, None)

app = FastAPI(title="API Service", version="1.0.0")

# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class RestaurantOut(BaseModel):
    id: int
    name: str
    cuisine: List[str]
    food: List[str]
    opening_hours_beginning: Optional[str]
    opening_hours_ending: Optional[str]
    image_url: Optional[str]
    rating: Optional[float]
    
    class Config:
        from_attributes = True

class FoodOut(BaseModel):
    id: int
    restaurant_id: int
    name: str
    description: Optional[str]
    cuisine_type: str
    food_type: str
    price: float
    is_available: bool
    image_url: Optional[str]
    
    class Config:
        from_attributes = True

class OrderItemIn(BaseModel):
    food_id: int
    quantity: int = Field(..., gt=0)

class OrderCreate(BaseModel):
    restaurant_id: int
    delivery_address: str
    payment_method: str  # "online" or "offline"
    items: List[OrderItemIn]

class OrderItemOut(BaseModel):
    food_id: int
    food_name: str
    quantity: int
    price_at_time: float
    
    class Config:
        from_attributes = True

class OrderOut(BaseModel):
    id: int
    creation_key: str
    user_id: Optional[int]
    restaurant_id: int
    order_time: datetime
    delivery_address: str
    total_amount: float
    status: str
    payment_method: str
    items: List[OrderItemOut]
    
    class Config:
        from_attributes = True

class OrderStatusOut(BaseModel):
    id: int
    status: str
    order_time: datetime
    delivery_address: str
    total_amount: float
    
    class Config:
        from_attributes = True

# ============================================================================
# RESTAURANT ENDPOINTS (FT-001, FT-002)
# ============================================================================

@app.get("/restaurants", response_model=List[RestaurantOut])
def list_restaurants(
    cuisine: Optional[str] = Query(None, description="Filter by cuisine type"),
    min_rating: Optional[float] = Query(None, ge=0, le=5),
    max_price: Optional[float] = Query(None, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_main_db)
):
    """
    FT-001: List restaurants with filtering by cuisine, rating, and price.
    """
    query = db.query(Restaurant)
    
    if cuisine:
        query = query.filter(Restaurant.cuisine.any(cuisine))
    if min_rating is not None:
        query = query.filter(Restaurant.rating >= min_rating)
    if max_price is not None:
        # Subquery to find restaurants with food under max_price
        from sqlalchemy import select
        subq = select(Food.restaurant_id).where(Food.price <= max_price).distinct()
        query = query.filter(Restaurant.id.in_(subq))
    
    offset = (page - 1) * page_size
    restaurants = query.offset(offset).limit(page_size).all()
    
    return restaurants

@app.get("/restaurants/{restaurant_id}/menu", response_model=List[FoodOut])
def get_menu(
    restaurant_id: int,
    food_type: Optional[str] = Query(None),
    available_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_main_db)
):
    """
    FT-002: Get restaurant menu with food details.
    """
    query = db.query(Food).filter(Food.restaurant_id == restaurant_id)
    
    if food_type:
        query = query.filter(Food.food_type == food_type)
    if available_only:
        query = query.filter(Food.is_available == True)
    
    offset = (page - 1) * page_size
    foods = query.offset(offset).limit(page_size).all()
    
    if not foods:
        raise HTTPException(status_code=404, detail="Restaurant or menu not found")
    
    return foods

@app.get("/restaurants/{restaurant_id}", response_model=RestaurantOut)
def get_restaurant(restaurant_id: int, db: Session = Depends(get_main_db)):
    """Get single restaurant details."""
    rest = db.query(Restaurant).filter(Restaurant.id == restaurant_id).first()
    if not rest:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return rest

# ============================================================================
# ORDER ENDPOINTS (FT-003 partial - creation via order_service, status via api)
# ============================================================================

@app.get("/orders/{order_id}/status", response_model=OrderStatusOut)
def get_order_status(order_id: int, db: Session = Depends(get_main_db)):
    """
    FT-005: View order status.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return OrderStatusOut(
        id=order.id,
        status=order.status.value,
        order_time=order.order_time,
        delivery_address=order.delivery_address,
        total_amount=float(order.total_amount)
    )

@app.get("/users/{user_id}/orders", response_model=List[OrderStatusOut])
def get_user_orders(
    user_id: int,
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_main_db)
):
    """Get all orders for a user, optionally filtered by status."""
    query = db.query(Order).filter(Order.user_id == user_id)
    
    if status:
        query = query.filter(Order.status == status)
    
    offset = (page - 1) * page_size
    orders = query.order_by(Order.order_time.desc()).offset(offset).limit(page_size).all()
    
    return [
        OrderStatusOut(
            id=o.id,
            status=o.status.value,
            order_time=o.order_time,
            delivery_address=o.delivery_address,
            total_amount=float(o.total_amount)
        ) for o in orders
    ]

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "api_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
