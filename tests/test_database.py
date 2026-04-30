"""
Tests for database models and initialization.
Run with: pytest tests/test_database.py -v
"""

import os
import sys
import uuid
from datetime import datetime
from decimal import Decimal

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.database import (
    MainBase, TrackingBase,
    User, Restaurant, RestaurantAdmin, Food, Order, OrderItem, Rating,
    Courier, TrackingOrder,
    CuisineType, FoodType, OrderStatus, PaymentMethod,
    init_session_factories
)
from common.database_init import create_enum_types, create_tracking_enum_types

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def main_engine():
    """Create a test main database engine."""
    url = os.getenv("TEST_MAIN_DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/test_main_db")
    engine = create_engine(url, echo=False)
    
    # Drop and recreate
    from sqlalchemy_utils import database_exists, create_database, drop_database
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)
    
    create_enum_types(engine)
    MainBase.metadata.create_all(bind=engine)
    
    yield engine
    
    engine.dispose()
    if database_exists(engine.url):
        drop_database(engine.url)

@pytest.fixture(scope="session")
def tracking_engine():
    """Create a test tracking database engine."""
    url = os.getenv("TEST_TRACKING_DATABASE_URL", "postgresql://postgres:postgres@localhost:5434/test_tracking_db")
    engine = create_engine(url, echo=False)
    
    from sqlalchemy_utils import database_exists, create_database, drop_database
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)
    
    create_tracking_enum_types(engine)
    TrackingBase.metadata.create_all(bind=engine)
    
    yield engine
    
    engine.dispose()
    if database_exists(engine.url):
        drop_database(engine.url)

@pytest.fixture
def main_session(main_engine):
    """Create a fresh session for each test."""
    Session = sessionmaker(bind=main_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def tracking_session(tracking_engine):
    """Create a fresh session for each test."""
    Session = sessionmaker(bind=tracking_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

# ============================================================================
# MAIN DB TESTS
# ============================================================================

class TestUserModel:
    def test_create_user(self, main_session):
        user = User(
            login="testuser",
            password="hashed_password",
            phone="+79001234567",
            address="Moscow, Red Square 1"
        )
        main_session.add(user)
        main_session.commit()
        
        assert user.id is not None
        assert user.login == "testuser"
        
    def test_user_unique_login(self, main_session):
        user1 = User(login="unique_user", password="pass1")
        main_session.add(user1)
        main_session.commit()
        
        user2 = User(login="unique_user", password="pass2")
        main_session.add(user2)
        with pytest.raises(Exception):
            main_session.commit()
        main_session.rollback()

class TestRestaurantModel:
    def test_create_restaurant(self, main_session):
        rest = Restaurant(
            name="Test Pizza",
            cuisine=[CuisineType.Italian, CuisineType.American],
            food=[FoodType.Pizza, FoodType.Sauce],
            opening_hours_beginning="10:00",
            opening_hours_ending="22:00",
            image_url="https://example.com/pizza.jpg",
            rating=Decimal("4.5")
        )
        main_session.add(rest)
        main_session.commit()
        
        assert rest.id is not None
        assert rest.name == "Test Pizza"
        assert len(rest.cuisine) == 2

class TestFoodModel:
    def test_create_food(self, main_session):
        rest = Restaurant(
            name="Sushi Bar",
            cuisine=[CuisineType.Japanese],
            food=[FoodType.Sushi]
        )
        main_session.add(rest)
        main_session.commit()
        
        food = Food(
            restaurant_id=rest.id,
            name="Philadelphia Roll",
            description="Salmon, cream cheese, avocado",
            cuisine_type=CuisineType.Japanese,
            food_type=FoodType.Sushi,
            price=Decimal("450.00"),
            is_available=True,
            image_url="https://example.com/sushi.jpg"
        )
        main_session.add(food)
        main_session.commit()
        
        assert food.id is not None
        assert food.restaurant_id == rest.id
        assert food.price == Decimal("450.00")

class TestOrderModel:
    def test_create_order(self, main_session):
        user = User(login="order_user", password="pass")
        rest = Restaurant(name="Burger King", cuisine=[CuisineType.American], food=[FoodType.Burger])
        main_session.add_all([user, rest])
        main_session.commit()
        
        order = Order(
            user_id=user.id,
            restaurant_id=rest.id,
            delivery_address="Moscow, Lenina 10",
            total_amount=Decimal("899.00"),
            status=OrderStatus.InPayment,
            payment_method=PaymentMethod.Online
        )
        main_session.add(order)
        main_session.commit()
        
        assert order.id is not None
        assert order.creation_key is not None
        assert order.status == OrderStatus.InPayment
        
    def test_order_items(self, main_session):
        user = User(login="item_user", password="pass")
        rest = Restaurant(name="Test Rest", cuisine=[CuisineType.Italian], food=[FoodType.Pizza])
        main_session.add_all([user, rest])
        main_session.commit()
        
        food = Food(
            restaurant_id=rest.id,
            name="Margherita",
            cuisine_type=CuisineType.Italian,
            food_type=FoodType.Pizza,
            price=Decimal("350.00")
        )
        main_session.add(food)
        main_session.commit()
        
        order = Order(
            user_id=user.id,
            restaurant_id=rest.id,
            delivery_address="Test Address",
            total_amount=Decimal("700.00"),
            status=OrderStatus.Created,
            payment_method=PaymentMethod.Offline
        )
        main_session.add(order)
        main_session.commit()
        
        item = OrderItem(
            order_id=order.id,
            food_id=food.id,
            quantity=2,
            price_at_time=Decimal("350.00")
        )
        main_session.add(item)
        main_session.commit()
        
        # Test relationship
        fetched_order = main_session.query(Order).filter_by(id=order.id).first()
        assert len(fetched_order.items) == 1
        assert fetched_order.items[0].food.name == "Margherita"

class TestRestaurantAdmin:
    def test_admin_assignment(self, main_session):
        user = User(login="admin_user", password="pass")
        rest = Restaurant(name="Admin Rest", cuisine=[CuisineType.French], food=[FoodType.Extra])
        main_session.add_all([user, rest])
        main_session.commit()
        
        admin = RestaurantAdmin(user_id=user.id, restaurant_id=rest.id)
        main_session.add(admin)
        main_session.commit()
        
        assert admin.user_id == user.id
        assert admin.restaurant_id == rest.id
        
        # Test relationship
        fetched_user = main_session.query(User).filter_by(id=user.id).first()
        assert len(fetched_user.admin_restaurants) == 1

class TestRating:
    def test_create_rating(self, main_session):
        user = User(login="rating_user", password="pass")
        rest = Restaurant(name="Rated Rest", cuisine=[CuisineType.Thai], food=[FoodType.Tea])
        main_session.add_all([user, rest])
        main_session.commit()
        
        rating = Rating(user_id=user.id, restaurant_id=rest.id, rating=5)
        main_session.add(rating)
        main_session.commit()
        
        assert rating.rating == 5

# ============================================================================
# TRACKING DB TESTS
# ============================================================================

class TestCourierModel:
    def test_create_courier(self, tracking_session):
        courier = Courier(
            restaurant_id=1,
            password="courier_pass"
        )
        tracking_session.add(courier)
        tracking_session.commit()
        
        assert courier.id is not None
        assert courier.restaurant_id == 1

class TestTrackingOrder:
    def test_create_tracking_order(self, tracking_session):
        courier = Courier(restaurant_id=1, password="pass")
        tracking_session.add(courier)
        tracking_session.commit()
        
        order = TrackingOrder(
            id=1001,
            restaurant_id=1,
            courier_id=courier.id,
            order_time=datetime.now(),
            delivery_address="Moscow, Tverskaya 5",
            phone="+79001234567",
            total_amount=Decimal("500.00"),
            status=OrderStatus.Pending,
            payment_method=PaymentMethod.Online,
            content={"items": [{"name": "Burger", "quantity": 1}]}
        )
        tracking_session.add(order)
        tracking_session.commit()
        
        assert order.id == 1001
        assert order.courier_id == courier.id
        assert order.content["items"][0]["name"] == "Burger"
        
    def test_order_courier_relationship(self, tracking_session):
        courier = Courier(restaurant_id=2, password="pass2")
        tracking_session.add(courier)
        tracking_session.commit()
        
        order1 = TrackingOrder(
            id=2001, restaurant_id=2, courier_id=courier.id,
            order_time=datetime.now(), delivery_address="Addr1",
            total_amount=Decimal("100.00"), status=OrderStatus.Confirmed,
            payment_method=PaymentMethod.Offline, content={}
        )
        order2 = TrackingOrder(
            id=2002, restaurant_id=2, courier_id=courier.id,
            order_time=datetime.now(), delivery_address="Addr2",
            total_amount=Decimal("200.00"), status=OrderStatus.Delivery,
            payment_method=PaymentMethod.Online, content={}
        )
        tracking_session.add_all([order1, order2])
        tracking_session.commit()
        
        fetched_courier = tracking_session.query(Courier).filter_by(id=courier.id).first()
        assert len(fetched_courier.orders) == 2

# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    def test_main_and_tracking_independent(self, main_session, tracking_session):
        """Test that main DB and tracking DB are independent."""
        user = User(login="integ_user", password="pass")
        main_session.add(user)
        main_session.commit()
        
        courier = Courier(restaurant_id=1, password="pass")
        tracking_session.add(courier)
        tracking_session.commit()
        
        # Verify they exist in their respective DBs
        assert main_session.query(User).filter_by(login="integ_user").first() is not None
        assert tracking_session.query(Courier).filter_by(id=courier.id).first() is not None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
