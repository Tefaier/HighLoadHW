"""
Comprehensive endpoint tests for all services.
Verifies that every endpoint returns expected status codes.
Run with: pytest tests/test_endpoints.py -v
"""

import os
import sys
import pytest
from datetime import datetime
from decimal import Decimal
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))

os.environ["MAIN_DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/test_endpoints_main".replace("test_endpoints_main","main_db")
os.environ["TRACKING_DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5434/test_endpoints_tracking".replace("test_endpoints_tracking","tracking_db")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.database import MainBase, TrackingBase, init_session_factories
from common.database_init import create_enum_types, create_tracking_enum_types

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def test_main_engine():
    url = os.environ["MAIN_DATABASE_URL"]
    engine = create_engine(url, echo=False)
    from sqlalchemy_utils import database_exists, create_database, drop_database
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)
    create_enum_types(engine)
    MainBase.metadata.create_all(bind=engine)
    yield engine
    try:
        engine.dispose()
        if database_exists(engine.url):
            drop_database(engine.url)
    except:
        pass

@pytest.fixture(scope="session")
def test_tracking_engine():
    url = os.environ["TRACKING_DATABASE_URL"]
    engine = create_engine(url, echo=False)
    from sqlalchemy_utils import database_exists, create_database, drop_database
    if database_exists(engine.url):
        drop_database(engine.url)
    create_database(engine.url)
    create_tracking_enum_types(engine)
    TrackingBase.metadata.create_all(bind=engine)
    yield engine
    try:
        engine.dispose()
        if database_exists(engine.url):
            drop_database(engine.url)
    except:
        pass

@pytest.fixture
def main_db(test_main_engine):
    Session = sessionmaker(bind=test_main_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def tracking_db(test_tracking_engine):
    Session = sessionmaker(bind=test_tracking_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def api_client(test_main_engine):
    from services.api_service.main import app, get_main_db
    from common.database import MainSessionLocal
    def override():
        db = MainSessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_main_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def order_client(test_main_engine):
    from services.order_service.main import app, get_main_db
    from common.database import MainSessionLocal
    def override():
        db = MainSessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_main_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def tracking_client(test_tracking_engine):
    from services.tracking_service.main import app, get_tracking_db
    from common.database import TrackingSessionLocal
    def override():
        db = TrackingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_tracking_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def sample_data(main_db):
    """Create sample user, restaurant, food for endpoint tests.
    Checks if data already exists before creating to avoid duplicates."""
    from common.database import User, Restaurant, Food, CuisineType, FoodType
    
    # Check if test data already exists (from previous test or session)
    existing_user = main_db.query(User).filter(User.login == "endpoint_user").first()
    
    if existing_user:
        # Reuse existing data
        existing_rest = main_db.query(Restaurant).filter(
            Restaurant.name == "Endpoint Pizza"
        ).first()
        existing_foods = main_db.query(Food).filter(
            Food.restaurant_id == existing_rest.id
        ).all() if existing_rest else []
        
        food_ids = [f.id for f in existing_foods]
        yield {
            "user_id": existing_user.id,
            "restaurant_id": existing_rest.id if existing_rest else None,
            "food_ids": food_ids
        }
        return  # Cleanup skipped - data was not created by this fixture
    
    # Create fresh test data
    user = User(login="endpoint_user", password="pass", phone="+79000000000")
    rest = Restaurant(
        name="Endpoint Pizza",
        cuisine=[CuisineType.Italian, CuisineType.American],
        food=[FoodType.Pizza, FoodType.Burger],
        opening_hours_beginning="10:00",
        opening_hours_ending="22:00",
        image_url="https://example.com/img.jpg",
        rating=Decimal("4.5")
    )
    main_db.add_all([user, rest])
    main_db.flush()  # Get IDs without committing
    
    food1 = Food(
        restaurant_id=rest.id, name="Margherita",
        cuisine_type=CuisineType.Italian, food_type=FoodType.Pizza,
        price=Decimal("350.00"), is_available=True,
        description="Classic pizza", image_url="https://example.com/pizza.jpg"
    )
    food2 = Food(
        restaurant_id=rest.id, name="Cheeseburger",
        cuisine_type=CuisineType.American, food_type=FoodType.Burger,
        price=Decimal("250.00"), is_available=True,
        description="Beef burger", image_url="https://example.com/burger.jpg"
    )
    main_db.add_all([food1, food2])
    main_db.commit()  # Commit so service sessions can see it
    
    yield {"user_id": user.id, "restaurant_id": rest.id, "food_ids": [food1.id, food2.id]}
    
    # Cleanup: delete in reverse order to respect FKs
    try:
        main_db.query(Food).filter(Food.restaurant_id == rest.id).delete(synchronize_session=False)
        main_db.query(Restaurant).filter(Restaurant.id == rest.id).delete(synchronize_session=False)
        main_db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
        main_db.commit()
    except:
        pass
# ============================================================================
# API SERVICE ENDPOINTS
# ============================================================================

class TestApiHealth:
    def test_health_returns_200(self, api_client):
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "api_service"

class TestApiRestaurants:
    def test_list_restaurants_empty_200(self, api_client):
        response = api_client.get("/restaurants")
        assert response.status_code == 200
        assert response.json() == []
    
    def test_list_restaurants_with_data_200(self, api_client, sample_data):
        response = api_client.get("/restaurants")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["name"] == "Endpoint Pizza"
    
    def test_list_restaurants_filter_cuisine_200(self, api_client, sample_data):
        response = api_client.get("/restaurants?cuisine=Italian")
        assert response.status_code == 200
        assert all("Italian" in r["cuisine"] for r in response.json())
    
    def test_list_restaurants_filter_rating_200(self, api_client, sample_data):
        response = api_client.get("/restaurants?min_rating=4.0")
        assert response.status_code == 200
    
    def test_list_restaurants_pagination_200(self, api_client, sample_data):
        response = api_client.get("/restaurants?page=1&page_size=10")
        assert response.status_code == 200
    
    def test_get_restaurant_200(self, api_client, sample_data):
        rid = sample_data["restaurant_id"]
        response = api_client.get(f"/restaurants/{rid}")
        assert response.status_code == 200
        assert response.json()["name"] == "Endpoint Pizza"
    
    def test_get_restaurant_404(self, api_client):
        response = api_client.get("/restaurants/999999")
        assert response.status_code == 404

class TestApiMenu:
    def test_get_menu_200(self, api_client, sample_data):
        rid = sample_data["restaurant_id"]
        response = api_client.get(f"/restaurants/{rid}/menu")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] in ["Margherita", "Cheeseburger"]
    
    def test_get_menu_filter_type_200(self, api_client, sample_data):
        rid = sample_data["restaurant_id"]
        response = api_client.get(f"/restaurants/{rid}/menu?food_type=Pizza")
        assert response.status_code == 200
        assert all(i["food_type"] == "Pizza" for i in response.json())
    
    def test_get_menu_available_only_200(self, api_client, sample_data):
        rid = sample_data["restaurant_id"]
        response = api_client.get(f"/restaurants/{rid}/menu?available_only=true")
        assert response.status_code == 200
    
    def test_get_menu_pagination_200(self, api_client, sample_data):
        rid = sample_data["restaurant_id"]
        response = api_client.get(f"/restaurants/{rid}/menu?page=1&page_size=5")
        assert response.status_code == 200
    
    def test_get_menu_404(self, api_client):
        response = api_client.get("/restaurants/999999/menu")
        assert response.status_code == 404

class TestApiOrderStatus:
    def test_get_order_status_200(self, api_client, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        # Create an order directly in DB for status query
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test Addr",
            total_amount=Decimal("600.00"),
            status=OrderStatus.Created,
            payment_method=PaymentMethod.Offline
        )
        main_db.add(order)
        main_db.commit()
        
        response = api_client.get(f"/orders/{order.id}/status")
        assert response.status_code == 200
        assert response.json()["status"] == "created"
    
    def test_get_order_status_404(self, api_client):
        response = api_client.get("/orders/999999/status")
        assert response.status_code == 404
    
    def test_get_user_orders_200(self, api_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.Finished,
            payment_method=PaymentMethod.Online
        )
        main_db.add(order)
        main_db.commit()
        
        response = api_client.get(f"/users/{sample_data['user_id']}/orders")
        assert response.status_code == 200
        assert len(response.json()) >= 1
    
    def test_get_user_orders_filter_status_200(self, api_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.Finished,
            payment_method=PaymentMethod.Online
        )
        main_db.add(order)
        main_db.commit()
        
        response = api_client.get(f"/users/{sample_data['user_id']}/orders?status=finished")
        assert response.status_code == 200
        assert all(o["status"] == "finished" for o in response.json())
    
    def test_get_user_orders_pagination_200(self, api_client, sample_data):
        response = api_client.get(f"/users/{sample_data['user_id']}/orders?page=1&page_size=5")
        assert response.status_code == 200

# ============================================================================
# ORDER SERVICE ENDPOINTS
# ============================================================================

class TestOrderHealth:
    def test_health_returns_200(self, order_client):
        response = order_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "order_service"

class TestOrderCreate:
    def test_create_order_offline_201(self, order_client, sample_data):
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Moscow, Test St 1",
            "payment_method": "offline",
            "items": [{"food_id": sample_data["food_ids"][0], "quantity": 2}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert data["total_amount"] == 700.00  # 350 * 2
        assert "creation_key" in data
        assert len(data["items"]) == 1
    
    def test_create_order_online_201(self, order_client, sample_data):
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Moscow, Test St 2",
            "payment_method": "online",
            "items": [{"food_id": sample_data["food_ids"][1], "quantity": 1}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 201
        assert response.json()["status"] == "in_payment"
    
    def test_create_order_multiple_items_201(self, order_client, sample_data):
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Moscow, Test St 3",
            "payment_method": "offline",
            "items": [
                {"food_id": sample_data["food_ids"][0], "quantity": 1},
                {"food_id": sample_data["food_ids"][1], "quantity": 2}
            ]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["total_amount"] == 850.00  # 350 + 250*2
        assert len(data["items"]) == 2
    
    def test_create_order_invalid_restaurant_404(self, order_client, sample_data):
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": 999999,
            "delivery_address": "Test",
            "payment_method": "offline",
            "items": [{"food_id": sample_data["food_ids"][0], "quantity": 1}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 404
    
    def test_create_order_invalid_user_404(self, order_client, sample_data):
        payload = {
            "user_id": 999999,
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Test",
            "payment_method": "offline",
            "items": [{"food_id": sample_data["food_ids"][0], "quantity": 1}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 404
    
    def test_create_order_invalid_payment_400(self, order_client, sample_data):
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Test",
            "payment_method": "crypto",
            "items": [{"food_id": sample_data["food_ids"][0], "quantity": 1}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 400
    
    def test_create_order_unavailable_food_400(self, order_client, sample_data, main_db):
        from common.database import Food, CuisineType, FoodType
        
        # Create unavailable food
        bad_food = Food(
            restaurant_id=sample_data["restaurant_id"],
            name="Sold Out Item",
            cuisine_type=CuisineType.Italian,
            food_type=FoodType.Pizza,
            price=Decimal("100.00"),
            is_available=False
        )
        main_db.add(bad_food)
        main_db.commit()
        
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Test",
            "payment_method": "offline",
            "items": [{"food_id": bad_food.id, "quantity": 1}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 400
    
    def test_create_order_wrong_restaurant_food_400(self, order_client, sample_data, main_db):
        from common.database import Restaurant, Food, CuisineType, FoodType
        
        # Create another restaurant with its own food
        other_rest = Restaurant(name="Other Rest", cuisine=[CuisineType.Chinese], food=[FoodType.Sushi])
        main_db.add(other_rest)
        main_db.commit()
        
        other_food = Food(
            restaurant_id=other_rest.id,
            name="Other Sushi",
            cuisine_type=CuisineType.Chinese,
            food_type=FoodType.Sushi,
            price=Decimal("200.00"),
            is_available=True
        )
        main_db.add(other_food)
        main_db.commit()
        
        # Try to order other restaurant's food from first restaurant
        payload = {
            "user_id": sample_data["user_id"],
            "restaurant_id": sample_data["restaurant_id"],
            "delivery_address": "Test",
            "payment_method": "offline",
            "items": [{"food_id": other_food.id, "quantity": 1}]
        }
        response = order_client.post("/orders", json=payload)
        assert response.status_code == 400

class TestOrderPayment:
    def test_payment_callback_success_200(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.InPayment,
            payment_method=PaymentMethod.Online
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.post(f"/orders/{order.id}/pay", json={
            "order_id": order.id,
            "success": True,
            "payment_ref": "ref-123"
        })
        assert response.status_code == 200
        assert response.json()["status"] == "paid"
    
    def test_payment_callback_fail_200(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.InPayment,
            payment_method=PaymentMethod.Online
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.post(f"/orders/{order.id}/pay", json={
            "order_id": order.id,
            "success": False
        })
        assert response.status_code == 200
        assert response.json()["status"] == "payment_failed"
    
    def test_payment_callback_wrong_status_400(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.Created,  # Not in_payment
            payment_method=PaymentMethod.Offline
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.post(f"/orders/{order.id}/pay", json={
            "order_id": order.id,
            "success": True
        })
        assert response.status_code == 400
    
    def test_payment_callback_404(self, order_client):
        response = order_client.post("/orders/999999/pay", json={
            "order_id": 999999,
            "success": True
        })
        assert response.status_code == 404

class TestOrderStatusUpdate:
    def test_update_status_200(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.Created,
            payment_method=PaymentMethod.Offline
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.patch(f"/orders/{order.id}/status", json={"status": "pending"})
        assert response.status_code == 200
        assert response.json()["new_status"] == "pending"
    
    def test_update_status_invalid_400(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.Created,
            payment_method=PaymentMethod.Offline
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.patch(f"/orders/{order.id}/status", json={"status": "invalid_status"})
        assert response.status_code == 400
    
    def test_update_status_404(self, order_client):
        response = order_client.patch("/orders/999999/status", json={"status": "pending"})
        assert response.status_code == 404

class TestOrderGet:
    def test_get_order_200(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test Get",
            total_amount=Decimal("500.00"),
            status=OrderStatus.Created,
            payment_method=PaymentMethod.Offline
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.get(f"/orders/{order.id}")
        assert response.status_code == 200
        assert response.json()["delivery_address"] == "Test Get"
        assert response.json()["total_amount"] == 500.00
    
    def test_get_order_404(self, order_client):
        response = order_client.get("/orders/999999")
        assert response.status_code == 404

class TestOrderRetry:
    def test_retry_pending_200(self, order_client, sample_data, main_db):
        from common.database import Order, OrderStatus, PaymentMethod
        
        # Create a 'created' order that needs retry
        order = Order(
            user_id=sample_data["user_id"],
            restaurant_id=sample_data["restaurant_id"],
            delivery_address="Test",
            total_amount=Decimal("100.00"),
            status=OrderStatus.Created,
            payment_method=PaymentMethod.Offline
        )
        main_db.add(order)
        main_db.commit()
        
        response = order_client.post("/internal/retry-pending")
        assert response.status_code == 200
        assert "processed" in response.json()
    
    def test_retry_pending_empty_200(self, order_client):
        response = order_client.post("/internal/retry-pending")
        assert response.status_code == 200
        assert response.json()["processed"] == 0

# ============================================================================
# TRACKING SERVICE ENDPOINTS
# ============================================================================

class TestTrackingHealth:
    def test_health_returns_200(self, tracking_client):
        response = tracking_client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "tracking_service"

class TestTrackingCouriers:
    def test_create_courier_201(self, tracking_client):
        response = tracking_client.post("/couriers", json={
            "restaurant_id": 1,
            "password": "courier123"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["restaurant_id"] == 1
        assert "id" in data
    
    def test_create_courier_multiple_201(self, tracking_client):
        for i in range(3):
            response = tracking_client.post("/couriers", json={
                "restaurant_id": i + 1,
                "password": f"pass{i}"
            })
            assert response.status_code == 201

class TestTrackingOrders:
    def test_create_tracking_order_201(self, tracking_client):
        response = tracking_client.post("/orders", json={
            "id": 1001,
            "restaurant_id": 1,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Moscow, Tverskaya 1",
            "phone": "+79001234567",
            "total_amount": 450.00,
            "status": "pending",
            "payment_method": "online",
            "content": [{"name": "Sushi", "quantity": 2}]
        })
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1001
        assert data["status"] == "pending"
    
    def test_create_tracking_order_duplicate_409(self, tracking_client,main_db):

        order_data = {
            "id": 2001,
            "restaurant_id": 1,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Addr",
            "total_amount": 100.00,
            "phone":None,
            "status": "pending",
            "payment_method": "offline",
            "content": []
        }
        # from services.tracking_service.main import TrackingOrderIn

        # order_data = TrackingOrderIn(id=2001,restaurant_id=1,order_time=datetime.now().isoformat(),delivery_address="Addr",status="pending",payment_method="offline",content=[],phone=None).dict()
        from common.database import Order
        main_db.query(Order).filter(Order.id == 2001).delete()#(synchronize_session=False)
        response = tracking_client.post("/orders", json=order_data)
        assert response.status_code//100 == 2
        
        # Duplicate
        response = tracking_client.post("/orders", json=order_data)
        assert response.status_code//100 == 4
    
    def test_create_tracking_order_invalid_status_400(self, tracking_client):
        response = tracking_client.post("/orders", json={
            "id": 3001,
            "restaurant_id": 1,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Addr",
            "total_amount": 100.00,
            "status": "invalid_status",
            "payment_method": "online",
            "content": []
        })
        assert response.status_code//100 == 4
    
    def test_get_tracking_order_200(self, tracking_client):
        # Create first
        tracking_client.post("/orders", json={
            "id": 4001,
            "restaurant_id": 1,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Addr",
            "total_amount": 200.00,
            "phone":None,
            "status": "confirmed",
            "payment_method": "offline",
            "content": [{"name": "Burger", "quantity": 1}]
        })
        
        response = tracking_client.get("/orders/4001")
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
    
    def test_get_tracking_order_404(self, tracking_client):
        response = tracking_client.get("/orders/999999")
        assert response.status_code == 404
    
    def test_update_tracking_status_200(self, tracking_client):
        # Create order
        tracking_client.post("/orders", json={
            "id": 5001,
            "restaurant_id": 1,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Addr",
            "total_amount": 150.00,
            "phone":None,
            "status": "pending",
            "payment_method": "online",
            "content": []
        })
        
        response = tracking_client.patch("/orders/5001/status", json={"status": "preparing"})
        assert response.status_code == 200
        assert response.json()["new_status"] == "preparing"
    
    def test_update_tracking_status_invalid_400(self, tracking_client):
        response = tracking_client.patch("/orders/5001/status", json={"status": "bad_status"})
        assert response.status_code//100 == 4
    
    def test_update_tracking_status_404(self, tracking_client):
        response = tracking_client.patch("/orders/999999/status", json={"status": "delivery"})
        assert response.status_code == 404
    
    def test_assign_courier_200(self, tracking_client):
        # Create courier
        courier_resp = tracking_client.post("/couriers", json={
            "restaurant_id": 10,
            "password": "pass"
        })
        courier_id = courier_resp.json()["id"]
        
        # Create order
        response = tracking_client.post("/orders", json={
            "id": 6001,
            "restaurant_id": 10,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Addr",
            "total_amount": 300.00,
            "phone":None,
            "status": "pending",
            "payment_method": "offline",
            "content": []
        })
        assert response.status_code//100 == 2
        
        response = tracking_client.post(f"/orders/6001/assign", json={"courier_id": courier_id})
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["courier_id"] == courier_id
    
    def test_assign_courier_404_order(self, tracking_client):
        response = tracking_client.post("/orders/999999/assign", json={"courier_id": 1})
        assert response.status_code == 404
    
    def test_assign_courier_404_courier(self, tracking_client):
        # Create order
        tracking_client.post("/orders", json={
            "id": 7001,
            "restaurant_id": 1,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Addr",
            "total_amount": 100.00,
            "status": "pending",
            "payment_method": "online",
            "content": []
        })
        
        response = tracking_client.post("/orders/7001/assign", json={"courier_id": 999999})
        assert response.status_code == 404

class TestTrackingCourierOrders:
    def test_get_courier_orders_200(self, tracking_client):
        # Create courier
        courier_resp = tracking_client.post("/couriers", json={
            "restaurant_id": 20,
            "password": "pass"
        })
        courier_id = courier_resp.json()["id"]
        
        # Create and assign orders
        for i in range(3):
            oid = 8000 + i
            tracking_client.post("/orders", json={
                "id": oid,
                "restaurant_id": 20,
                "order_time": datetime.now().isoformat(),
                "delivery_address": f"Addr {i}",
                "total_amount": 100.00 + i * 50,
                "phone":None,
                "status": "pending",
                "payment_method": "online",
                "content": []
            })
            tracking_client.post(f"/orders/{oid}/assign", json={"courier_id": courier_id})
        
        response = tracking_client.get(f"/couriers/{courier_id}/orders")
        assert response.status_code == 200
        assert len(response.json()) == 3
    
    def test_get_courier_orders_filter_status_200(self, tracking_client):
        # Create courier
        courier_resp = tracking_client.post("/couriers", json={
            "restaurant_id": 30,
            "password": "pass"
        })
        courier_id = courier_resp.json()["id"]
        
        # Create orders with different statuses
        for i, status in enumerate(["confirmed", "confirmed", "delivery"]):
            oid = 9000 + i
            tracking_client.post("/orders", json={
                "id": oid,
                "restaurant_id": 30,
                "order_time": datetime.now().isoformat(),
                "delivery_address": "Addr",
                "total_amount": 100.00,
                "status": "pending",
                "payment_method": "online",
                "content": []
            })
            tracking_client.post(f"/orders/{oid}/assign", json={"courier_id": courier_id})
            if status != "confirmed":
                tracking_client.patch(f"/orders/{oid}/status", json={"status": status})
        
        response = tracking_client.get(f"/couriers/{courier_id}/orders?status=confirmed")
        assert response.status_code == 200
        assert all(o["status"] == "confirmed" for o in response.json())
    
    def test_get_courier_orders_empty_200(self, tracking_client):
        # Create courier with no orders
        courier_resp = tracking_client.post("/couriers", json={
            "restaurant_id": 40,
            "password": "pass"
        })
        courier_id = courier_resp.json()["id"]
        
        response = tracking_client.get(f"/couriers/{courier_id}/orders")
        assert response.status_code == 200
        assert response.json() == []

class TestTrackingRestaurantOrders:
    def test_get_restaurant_orders_200(self, tracking_client):
        # Create orders for restaurant 50
        for i in range(5):
            tracking_client.post("/orders", json={
                "id": 10000 + i,
                "restaurant_id": 50,
                "order_time": datetime.now().isoformat(),
                "delivery_address": f"Addr {i}",
                "total_amount": 100.00,
                "status": "pending",
                "phone":None,
                "payment_method": "online",
                "content": []
            })
        
        response = tracking_client.get("/restaurants/50/orders")
        assert response.status_code == 200
        assert len(response.json()) == 5
    
    def test_get_restaurant_orders_filter_status_200(self, tracking_client):
        # Create orders with different statuses
        for i, status in enumerate(["pending", "pending", "confirmed", "finished", "cancelled"]):
            tracking_client.post("/orders", json={
                "id": 11000 + i,
                "restaurant_id": 60,
                "order_time": datetime.now().isoformat(),
                "delivery_address": "Addr",
                "total_amount": 100.00,
                "status": status,
                "phone":None,
                "payment_method": "online",
                "content": []
            })
        
        # Default filter excludes finished and cancelled
        response = tracking_client.get("/restaurants/60/orders")
        assert response.status_code == 200
        # Should get pending, pending, confirmed = 3
        assert len(response.json()) == 3
    
    def test_get_restaurant_orders_empty_200(self, tracking_client):
        response = tracking_client.get("/restaurants/99999/orders")
        assert response.status_code == 200
        assert response.json() == []

class TestTrackingBrokerSync:
    def test_sync_order_from_broker_200(self, tracking_client):
        response = tracking_client.post("/internal/sync-order", json={
            "event": "order_created",
            "order_id": 50001,
            "restaurant_id": 1,
            "status": "pending"
        })
        assert response.status_code == 200
        assert response.json()["action"] == "created"
    
    def test_sync_order_update_existing_200(self, tracking_client):
        # Create via sync
        tracking_client.post("/internal/sync-order", json={
            "order_id": 50002,
            "restaurant_id": 1,
            "status": "pending"
        })
        
        # Update via sync
        response = tracking_client.post("/internal/sync-order", json={
            "order_id": 50002,
            "restaurant_id": 1,
            "status": "confirmed"
        })
        assert response.status_code == 200
        assert response.json()["action"] == "updated"

# ============================================================================
# CROSS-SERVICE ENDPOINTS
# ============================================================================

class TestCrossServiceEndpoints:
    def test_all_health_checks_200(self, api_client, order_client, tracking_client):
        """Verify all three services respond to health checks."""
        assert api_client.get("/health").status_code == 200
        assert order_client.get("/health").status_code == 200
        assert tracking_client.get("/health").status_code == 200
    
    def test_api_does_not_have_order_endpoints_404(self, api_client):
        """API service should not expose order creation."""
        response = api_client.post("/orders", json={})
        assert response.status_code == 404
    
    def test_order_does_not_have_restaurant_endpoints_404(self, order_client):
        """Order service should not expose restaurant browsing."""
        response = order_client.get("/restaurants")
        assert response.status_code == 404
    
    def test_tracking_does_not_have_menu_endpoints_404(self, tracking_client):
        """Tracking service should not expose menu browsing."""
        response = tracking_client.get("/restaurants/1/menu")
        assert response.status_code == 404

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
