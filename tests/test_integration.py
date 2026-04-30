"""
Integration tests for the microservices.
Tests service-to-service communication and data flow.
Run with: pytest tests/test_integration.py -v
"""

import os
import sys
import pytest
from datetime import datetime
from decimal import Decimal


os.environ["MAIN_DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5433/main_db"
os.environ["TRACKING_DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5434/tracking_db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'common'))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.database import MainBase, TrackingBase
from common.database_init import create_enum_types, create_tracking_enum_types

# ============================================================================
# SETUP TEST DATABASES
# ============================================================================

@pytest.fixture(scope="session")
def test_main_engine():
    url = "postgresql://postgres:postgres@localhost:5433/test_main_integration".replace("test_main_integration","main_db")
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
    url = "postgresql://postgres:postgres@localhost:5434/test_tracking_integration".replace("test_tracking_integration","tracking_db")
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
def main_db_session(test_main_engine):
    Session = sessionmaker(bind=test_main_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def tracking_db_session(test_tracking_engine):
    Session = sessionmaker(bind=test_tracking_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

# ============================================================================
# SERVICE CLIENTS (using TestClient)
# ============================================================================

@pytest.fixture
def api_client(test_main_engine):
    """Create API service test client with test DB."""
    from services.api_service.main import app, get_main_db
    from common.database import MainSessionLocal
    
    # Override dependency
    def override_get_db():
        db = MainSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_main_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()

@pytest.fixture
def order_client(test_main_engine):
    """Create Order service test client with test DB."""
    from services.order_service.main import app, get_main_db
    from common.database import MainSessionLocal
    
    def override_get_db():
        db = MainSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_main_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()

@pytest.fixture
def tracking_client(test_tracking_engine):
    """Create Tracking service test client with test DB."""
    from services.tracking_service.main import app, get_tracking_db
    from common.database import TrackingSessionLocal
    
    def override_get_db():
        db = TrackingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_tracking_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()

# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestEndToEndOrderFlow:
    """Test the complete order flow across all services."""
    
    def test_create_user_and_restaurant(self, api_client, main_db_session):
        """Setup: Create user and restaurant via API (or directly in DB)."""
        from common.database import User, Restaurant, Food, CuisineType, FoodType
        
        # Create user directly in DB for simplicity
        user = User(login="e2e_user", password="pass", phone="+79000000000")
        rest = Restaurant(
            name="E2E Pizza",
            cuisine=[CuisineType.Italian],
            food=[FoodType.Pizza],
            opening_hours_beginning="09:00",
            opening_hours_ending="23:00",
            rating=Decimal("4.8")
        )
        main_db_session.add_all([user, rest])
        main_db_session.commit()
        
        # Create food
        food = Food(
            restaurant_id=rest.id,
            name="Pepperoni",
            cuisine_type=CuisineType.Italian,
            food_type=FoodType.Pizza,
            price=Decimal("500.00"),
            is_available=True
        )
        main_db_session.add(food)
        main_db_session.commit()
        
        # Verify via API
        response = api_client.get(f"/restaurants/{rest.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "E2E Pizza"
        
        return {"user_id": user.id, "restaurant_id": rest.id, "food_id": food.id}
    
    def test_full_order_lifecycle(self, api_client, order_client, tracking_client, main_db_session, tracking_db_session):
        """
        Complete flow:
        1. Create user, restaurant, food
        2. Create order via order_service
        3. Verify order in api_service
        4. Sync to tracking_service
        5. Assign courier
        6. Update status
        7. Verify status in api_service
        """
        from common.database import User, Restaurant, Food, Courier, CuisineType, FoodType
        
        # Setup data
        user = User(login="lifecycle_user", password="pass")
        rest = Restaurant(name="Lifecycle Rest", cuisine=[CuisineType.Japanese], food=[FoodType.Sushi])
        main_db_session.add_all([user, rest])
        main_db_session.commit()
        
        food = Food(
            restaurant_id=rest.id, name="Salmon Roll",
            cuisine_type=CuisineType.Japanese, food_type=FoodType.Sushi,
            price=Decimal("300.00"), is_available=True
        )
        main_db_session.add(food)
        main_db_session.commit()
        
        # 1. Create order
        order_data = {
            "user_id": user.id,
            "restaurant_id": rest.id,
            "delivery_address": "Moscow, Test Street 1",
            "payment_method": "offline",
            "items": [{"food_id": food.id, "quantity": 2}]
        }
        response = order_client.post("/orders", json=order_data)
        assert response.status_code == 201
        order = response.json()
        order_id = order["id"]
        assert order["status"] == "created"
        assert order["total_amount"] == 600.00
        
        # 2. Verify in api_service
        response = api_client.get(f"/orders/{order_id}/status")
        assert response.status_code == 200
        assert response.json()["status"] == "created"
        
        # 3. Create courier and sync order to tracking
        courier_data = {"restaurant_id": rest.id, "password": "courier_pass"}
        response = tracking_client.post("/couriers", json=courier_data)
        assert response.status_code == 201
        courier_id = response.json()["id"]
        
        # Sync order to tracking service
        tracking_order_data = {
            "id": order_id,
            "restaurant_id": rest.id,
            "order_time": datetime.now().isoformat(),
            "delivery_address": "Moscow, Test Street 1",
            "phone": "+79000000000",
            "total_amount": 600.00,
            "status": "pending",
            "payment_method": "offline",
            "content": [{"name": "Salmon Roll", "quantity": 2}]
        }
        response = tracking_client.post("/orders", json=tracking_order_data)
        assert response.status_code == 201
        
        # 4. Assign courier
        response = tracking_client.post(f"/orders/{order_id}/assign", json={"courier_id": courier_id})
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        
        # 5. Update status to delivery
        response = tracking_client.patch(f"/orders/{order_id}/status", json={"status": "delivery"})
        assert response.status_code == 200
        
        # 6. Verify in tracking
        response = tracking_client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "delivery"
        assert response.json()["courier_id"] == courier_id

class TestServiceIsolation:
    """Test that services are properly isolated."""
    
    def test_api_service_only_reads_main_db(self, api_client):
        """API service should not have access to tracking DB endpoints."""
        # api_service doesn't have courier endpoints
        response = api_client.get("/couriers/1/orders")
        assert response.status_code == 404  # Not found in api_service
    
    def test_tracking_service_only_reads_tracking_db(self, tracking_client):
        """Tracking service should not have restaurant browsing."""
        response = tracking_client.get("/restaurants")
        assert response.status_code == 404  # Not found in tracking_service

class TestBrokerFailureScenario:
    """Test the broker failure retry scenario from the sequence diagram."""
    
    def test_order_created_but_broker_fails(self, order_client, main_db_session):
        """
        When broker fails, order stays in 'created' status.
        Retry endpoint should pick it up and send to broker.
        """
        from common.database import User, Restaurant, Food, OrderStatus, CuisineType, FoodType
        
        user = User(login="broker_user", password="pass")
        rest = Restaurant(name="Broker Rest", cuisine=[CuisineType.American], food=[FoodType.Burger])
        main_db_session.add_all([user, rest])
        main_db_session.commit()
        
        food = Food(
            restaurant_id=rest.id, name="Cheeseburger",
            cuisine_type=CuisineType.American, food_type=FoodType.Burger,
            price=Decimal("250.00"), is_available=True
        )
        main_db_session.add(food)
        main_db_session.commit()
        
        # Create order (offline payment -> status 'created')
        order_data = {
            "user_id": user.id,
            "restaurant_id": rest.id,
            "delivery_address": "Test Address",
            "payment_method": "offline",
            "items": [{"food_id": food.id, "quantity": 1}]
        }
        response = order_client.post("/orders", json=order_data)
        assert response.status_code == 201
        order_id = response.json()["id"]
        
        # Simulate broker failure: order should still be 'created'
        response = order_client.get(f"/orders/{order_id}")
        assert response.json()["status"] == "created"
        
        # Call retry endpoint
        response = order_client.post("/internal/retry-pending")
        assert response.status_code == 200
        
        # After retry, order should be 'pending' (sent to broker)
        response = order_client.get(f"/orders/{order_id}")
        assert response.json()["status"] == "pending"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
