"""
Order Service - Handles order lifecycle:
- FT-003: Create orders, payment handling
- FT-004: Trigger notifications on status change
- Broker communication with tracking_service
"""

import os
import sys
import json
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

sys.path.insert(0,  os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from common.database import (
    get_main_db, get_main_engine, init_session_factories,
    User, Restaurant, Food, Order, OrderItem,
     OrderStatus, PaymentMethod
)

# Message broker client (Kafka/RabbitMQ abstraction)
class MessageBroker:
    """Simple message broker client. In production, use Kafka or RabbitMQ."""
    
    def __init__(self):
        self.broker_url = os.getenv("BROKER_URL", "kafka://kafka:9092")
        self.enabled = os.getenv("BROKER_ENABLED", "true").lower() == "true"
    
    async def publish_order_created(self, order_id: int, restaurant_id: int, status: str):
        """Publish order creation event to broker for tracking_service."""
        if not self.enabled:
            print(f"[BROKER] Would publish: order_created {order_id}")
            return
        
        message = {
            "event": "order_created",
            "order_id": order_id,
            "restaurant_id": restaurant_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        # In production: kafka_producer.send("orders", message)
        print(f"[BROKER] Published: {json.dumps(message)}")
    
    async def publish_status_changed(self, order_id: int, old_status: str, new_status: str):
        """Publish status change for notifications."""
        if not self.enabled:
            print(f"[BROKER] Would publish: status_changed {order_id} {old_status} -> {new_status}")
            return
        
        message = {
            "event": "status_changed",
            "order_id": order_id,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        print(f"[BROKER] Published: {json.dumps(message)}")

broker = MessageBroker()

# Initialize DB
main_engine = get_main_engine(os.getenv("MAIN_DATABASE_URL", "postgresql://postgres:postgres@main_db:5432/main_db"))
init_session_factories(main_engine, None)

app = FastAPI(title="Order Service", version="1.0.0")

# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class OrderItemIn(BaseModel):
    food_id: int
    quantity: int = Field(..., gt=0)

class OrderCreate(BaseModel):
    user_id: int
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

class PaymentCallback(BaseModel):
    order_id: int
    success: bool
    payment_ref: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str

# ============================================================================
# ORDER CREATION (FT-003)
# ============================================================================

@app.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_in: OrderCreate,
    # background_tasks: BackgroundTasks,
    db: Session = Depends(get_main_db)
):
    """
    FT-003: Create a new order with items.
    Validates food availability, calculates total, handles payment method.
    """
    # Validate restaurant exists
    restaurant = db.query(Restaurant).filter(Restaurant.id == order_in.restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    # Validate user exists
    user = db.query(User).filter(User.id == order_in.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate payment method
    try:
        payment_method = PaymentMethod(order_in.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    
    # Validate items and calculate total
    total_amount = Decimal("0")
    order_items = []
    
    for item_in in order_in.items:
        food = db.query(Food).filter(
            Food.id == item_in.food_id,
            Food.restaurant_id == order_in.restaurant_id,
            Food.is_available == True
        ).first()
        
        if not food:
            raise HTTPException(
                status_code=400, 
                detail=f"Food item {item_in.food_id} not found or not available in this restaurant"
            )
        
        item_total = food.price * item_in.quantity
        total_amount += item_total
        
        order_items.append({
            "food_id": food.id,
            "quantity": item_in.quantity,
            "price_at_time": food.price,
            "food_name": food.name
        })
    
    # Determine initial status based on payment method
    if payment_method == PaymentMethod.Online:
        initial_status = OrderStatus.InPayment
    else:
        initial_status = OrderStatus.Created
    
    # Create order
    order = Order(
        user_id=order_in.user_id,
        restaurant_id=order_in.restaurant_id,
        delivery_address=order_in.delivery_address,
        total_amount=total_amount,
        status=initial_status,
        payment_method=payment_method
    )
    db.add(order)
    db.flush()  # Get order.id without committing
    
    # Create order items
    for item_data in order_items:
        item = OrderItem(
            order_id=order.id,
            food_id=item_data["food_id"],
            quantity=item_data["quantity"],
            price_at_time=item_data["price_at_time"]
        )
        db.add(item)
    
    db.commit()
    db.refresh(order)
    
    # Publish to broker for tracking_service (async)
    if initial_status == OrderStatus.Created:
        await broker.publish_order_created(order.id, order.restaurant_id, order.status.value)
    
    # Build response
    return OrderOut(
        id=order.id,
        creation_key=str(order.creation_key),
        user_id=order.user_id,
        restaurant_id=order.restaurant_id,
        order_time=order.order_time,
        delivery_address=order.delivery_address,
        total_amount=float(order.total_amount),
        status=order.status.value,
        payment_method=order.payment_method.value,
        items=[
            OrderItemOut(
                food_id=oi.food_id,
                food_name=next(i["food_name"] for i in order_items if i["food_id"] == oi.food_id),
                quantity=oi.quantity,
                price_at_time=float(oi.price_at_time)
            ) for oi in order.items
        ]
    )

# ============================================================================
# PAYMENT HANDLING
# ============================================================================

@app.post("/orders/{order_id}/pay")
async def process_payment(
    order_id: int,
    callback: PaymentCallback,
    db: Session = Depends(get_main_db)
):
    """
    Payment system callback. Updates order status after payment.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.InPayment:
        raise HTTPException(status_code=400, detail="Order is not awaiting payment")
    
    if callback.success:
        old_status = order.status.value
        order.status = OrderStatus.Created
        db.commit()
        
        # Publish status change for notifications (FT-004)
        await broker.publish_status_changed(order.id, old_status, order.status.value)
        
        # Publish to tracking service
        await broker.publish_order_created(order.id, order.restaurant_id, order.status.value)
        
        return {"status": "paid", "order_id": order_id}
    else:
        order.status = OrderStatus.Cancelled
        db.commit()
        return {"status": "payment_failed", "order_id": order_id}

# ============================================================================
# STATUS MANAGEMENT
# ============================================================================

@app.patch("/orders/{order_id}/status")
async def update_status(
    order_id: int,
    update: StatusUpdate,
    db: Session = Depends(get_main_db)
):
    """
    Update order status. Publishes change to broker for notifications.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    try:
        new_status = OrderStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    old_status = order.status.value
    order.status = new_status
    db.commit()
    
    # Publish status change for notifications (FT-004)
    await broker.publish_status_changed(order.id, old_status, new_status.value)
    
    return {
        "order_id": order_id,
        "old_status": old_status,
        "new_status": new_status.value
    }

@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_main_db)):
    """Get full order details."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return OrderOut(
        id=order.id,
        creation_key=str(order.creation_key),
        user_id=order.user_id,
        restaurant_id=order.restaurant_id,
        order_time=order.order_time,
        delivery_address=order.delivery_address,
        total_amount=float(order.total_amount),
        status=order.status.value,
        payment_method=order.payment_method.value,
        items=[
            OrderItemOut(
                food_id=oi.food_id,
                food_name=oi.food.name,
                quantity=oi.quantity,
                price_at_time=float(oi.price_at_time)
            ) for oi in order.items
        ]
    )

# ============================================================================
# CRON TASK ENDPOINTS (for broker retry logic)
# ============================================================================

@app.post("/internal/retry-pending")
async def retry_pending_orders(db: Session = Depends(get_main_db)):
    """
    Cron task: Retry sending 'created' orders to broker.
    Handles broker failure scenario from sequence diagram.
    """
    pending_orders = db.query(Order).filter(
        Order.status == OrderStatus.Created
    ).all()
    
    results = []
    for order in pending_orders:
        try:
            await broker.publish_order_created(order.id, order.restaurant_id, order.status.value)
            # Update to pending after successful broker publish
            order.status = OrderStatus.Pending
            db.commit()
            results.append({"order_id": order.id, "result": "sent_to_broker"})
        except Exception as e:
            results.append({"order_id": order.id, "result": "failed", "error": str(e)})
    
    return {"processed": len(results), "results": results}

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "order_service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
