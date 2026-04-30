"""
Common ORM layer for HighLoad HW.
Contains SQLAlchemy models for Main DB and Tracking DB.
"""

import enum
import uuid

from sqlalchemy import (
    create_engine, Column, BigInteger, String, Text, DECIMAL, Boolean,
    ForeignKey, Enum, ARRAY, TIMESTAMP, Integer, JSON, UniqueConstraint,
    PrimaryKeyConstraint, Index, text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.dialects.postgresql import UUID

# ============================================================================
# ENUMS
# ============================================================================

class CuisineType(str, enum.Enum):
    Italian = "Italian"
    Chinese = "Chinese"
    Japanese = "Japanese"
    Mexican = "Mexican"
    Indian = "Indian"
    French = "French"
    Thai = "Thai"
    Mediterranean = "Mediterranean"
    American = "American"
    Greek = "Greek"

class FoodType(str, enum.Enum):
    Pizza = "Pizza"
    Burger = "Burger"
    Sushi = "Sushi"
    Tea = "Tea"
    SweetDrink = "Sweet drink"
    Extra = "Extra"
    Sauce = "Sauce"

class OrderStatus(str, enum.Enum):
    InPayment = "in_payment"
    Created = "created"
    Pending = "pending"
    Confirmed = "confirmed"
    Preparing = "preparing"
    Delivery = "delivery"
    Finished = "finished"
    Cancelled = "cancelled"

class PaymentMethod(str, enum.Enum):
    Online = "online"
    Offline = "offline"


def get_enum_values(enum_class):
    return [e.value for e in enum_class]

# ============================================================================
# MAIN DB BASE & MODELS (shared by api_service and order_service)
# ============================================================================

MainBase = declarative_base()

class User(MainBase):
    __tablename__ = "user"
    
    id = Column(BigInteger, primary_key=True)
    login = Column(String(100), nullable=False, unique=True)
    password = Column(String(100), nullable=False)
    phone = Column(String(20))
    address = Column(Text)
    
    orders = relationship("Order", back_populates="user")
    ratings = relationship("Rating", back_populates="user")
    admin_restaurants = relationship("RestaurantAdmin", back_populates="user")

class Restaurant(MainBase):
    __tablename__ = "restaurant"
    
    id = Column(BigInteger, primary_key=True)
    name = Column(String(200), nullable=False)
    cuisine = Column(ARRAY(Enum(CuisineType, name="cuisine_types", create_type=False,values_callable=get_enum_values)), nullable=False)
    food = Column(ARRAY(Enum(FoodType, name="food_types", create_type=False,values_callable=get_enum_values)), nullable=False)
    opening_hours_beginning = Column(String(5))  # HH:MM format since composite types are tricky in ORM
    opening_hours_ending = Column(String(5))
    image_url = Column(Text)
    rating = Column(DECIMAL(2, 1))
    
    food_items = relationship("Food", back_populates="restaurant", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="restaurant")
    ratings = relationship("Rating", back_populates="restaurant")
    admins = relationship("RestaurantAdmin", back_populates="restaurant")

class RestaurantAdmin(MainBase):
    __tablename__ = "restaurant_admin"
    
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    restaurant_id = Column(BigInteger, ForeignKey("restaurant.id", ondelete="CASCADE"), primary_key=True)
    
    user = relationship("User", back_populates="admin_restaurants")
    restaurant = relationship("Restaurant", back_populates="admins")
    
    __table_args__ = (
        Index("idx_restaurant_admin_restaurant_id", "restaurant_id"),
    )

class Food(MainBase):
    __tablename__ = "food"
    
    id = Column(BigInteger, primary_key=True)
    restaurant_id = Column(BigInteger, ForeignKey("restaurant.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    cuisine_type = Column(Enum(CuisineType, name="cuisine_types", create_type=False,values_callable=get_enum_values), nullable=False)
    food_type = Column(Enum(FoodType, name="food_types", create_type=False,values_callable=get_enum_values), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    is_available = Column(Boolean, default=True)
    image_url = Column(Text)
    
    restaurant = relationship("Restaurant", back_populates="food_items")
    order_items = relationship("OrderItem", back_populates="food")
    
    __table_args__ = (
        Index("idx_food_restaurant_id", "restaurant_id"),
    )

class Order(MainBase):
    __tablename__ = "order"
    
    id = Column(BigInteger, primary_key=True)
    creation_key = Column(UUID(as_uuid=True), unique=True, default=uuid.uuid4)
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="SET NULL"))
    restaurant_id = Column(BigInteger, ForeignKey("restaurant.id", ondelete="RESTRICT"), nullable=False)
    order_time = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    delivery_address = Column(Text, nullable=False)
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(Enum(OrderStatus, name="order_status", create_type=False,values_callable=get_enum_values), nullable=False)
    payment_method = Column(Enum(PaymentMethod, name="payment_methods", create_type=False,values_callable=get_enum_values), nullable=False)
    
    user = relationship("User", back_populates="orders")
    restaurant = relationship("Restaurant", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_order_user_id_status", "user_id", "status"),
    )

class OrderItem(MainBase):
    __tablename__ = "order_item"
    
    order_id = Column(BigInteger, ForeignKey("order.id", ondelete="CASCADE"), primary_key=True)
    food_id = Column(BigInteger, ForeignKey("food.id", ondelete="RESTRICT"), primary_key=True)
    quantity = Column(Integer, nullable=False)
    price_at_time = Column(DECIMAL(10, 2), nullable=False)
    
    order = relationship("Order", back_populates="items")
    food = relationship("Food", back_populates="order_items")

class Rating(MainBase):
    __tablename__ = "rating"
    
    user_id = Column(BigInteger, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    restaurant_id = Column(BigInteger, ForeignKey("restaurant.id", ondelete="CASCADE"), primary_key=True)
    rating = Column(Integer, nullable=False)
    
    user = relationship("User", back_populates="ratings")
    restaurant = relationship("Restaurant", back_populates="ratings")

# ============================================================================
# TRACKING DB BASE & MODELS (separate DB for tracking_service)
# ============================================================================

TrackingBase = declarative_base()

class Courier(TrackingBase):
    __tablename__ = "courier"
    
    id = Column(BigInteger, primary_key=True)
    restaurant_id = Column(BigInteger, nullable=False)
    password = Column(String(100), nullable=False)
    
    orders = relationship("TrackingOrder", back_populates="courier")
    
    __table_args__ = (
        Index("idx_courier_restaurant_id", "restaurant_id"),
    )

class TrackingOrder(TrackingBase):
    __tablename__ = "order"
    
    id = Column(BigInteger, primary_key=True)
    restaurant_id = Column(BigInteger, nullable=False)
    courier_id = Column(BigInteger, ForeignKey("courier.id", ondelete="RESTRICT"))
    order_time = Column(TIMESTAMP(timezone=True), nullable=False)
    delivery_address = Column(Text, nullable=False)
    phone = Column(String(20))
    total_amount = Column(DECIMAL(10, 2), nullable=False)
    status = Column(Enum(OrderStatus, name="order_statuses", create_type=False,values_callable=get_enum_values), nullable=False)
    payment_method = Column(Enum(PaymentMethod, name="payment_methods", create_type=False,values_callable=get_enum_values), nullable=False)
    content = Column(JSON, nullable=False)  # Full order content with items
    
    courier = relationship("Courier", back_populates="orders")
    
    __table_args__ = (
        Index("idx_order_courier_id", "courier_id"),
        Index("idx_order_restaurant_id_status", "restaurant_id", "status"),
    )

# ============================================================================
# SESSION FACTORIES
# ============================================================================

def get_main_engine(database_url: str = None):
    if database_url is None:
        database_url = (
            "postgresql://postgres:postgres@main_db:5432/main_db"
        )
    return create_engine(database_url, pool_size=20, max_overflow=10)

def get_tracking_engine(database_url: str = None):
    if database_url is None:
        database_url = (
            "postgresql://postgres:postgres@tracking_db:5432/tracking_db"
        )
    return create_engine(database_url, pool_size=20, max_overflow=10)

MainSessionLocal = None
TrackingSessionLocal = None

def init_session_factories(main_engine=None, tracking_engine=None):
    global MainSessionLocal, TrackingSessionLocal
    if main_engine:
        MainSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=main_engine)
    if tracking_engine:
        TrackingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=tracking_engine)

def get_main_db():
    db = MainSessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_tracking_db():
    db = TrackingSessionLocal()
    try:
        yield db
    finally:
        db.close()
