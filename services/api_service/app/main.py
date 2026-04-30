from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.common.db import Base, make_engine, make_session_factory, wait_for_database
from services.common.db1_models import Food, Restaurant, RestaurantAdmin, User
from services.common.settings import settings

from .schemas import FoodCreateIn, FoodPatchIn, RestaurantCreateIn, RestaurantPatchIn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)

app = FastAPI(title='API Service', version='0.1.0')


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event('startup')
def startup() -> None:
    wait_for_database(engine)
    Base.metadata.create_all(bind=engine)


@app.get('/healthz')
def healthz():
    return {'status': 'ok', 'service': 'api-service'}


@app.post('/admin/restaurants', status_code=status.HTTP_201_CREATED)
def create_restaurant(payload: RestaurantCreateIn, db: Session = Depends(get_db)):
    restaurant = Restaurant(**payload.model_dump())
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    return {'id': restaurant.id}


@app.patch('/admin/restaurants/{restaurant_id}')
def patch_restaurant(restaurant_id: int, payload: RestaurantPatchIn, db: Session = Depends(get_db)):
    restaurant = db.get(Restaurant, restaurant_id)
    if not restaurant:
        raise HTTPException(status_code=404, detail='restaurant not found')
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(restaurant, k, v)
    db.commit()
    return {'ok': True}


@app.post('/admin/foods', status_code=status.HTTP_201_CREATED)
def create_food(payload: FoodCreateIn, db: Session = Depends(get_db)):
    if not db.get(Restaurant, payload.restaurant_id):
        raise HTTPException(status_code=404, detail='restaurant not found')
    food = Food(**payload.model_dump())
    db.add(food)
    db.commit()
    db.refresh(food)
    return {'id': food.id}


@app.patch('/admin/foods/{food_id}')
def patch_food(food_id: int, payload: FoodPatchIn, db: Session = Depends(get_db)):
    food = db.get(Food, food_id)
    if not food:
        raise HTTPException(status_code=404, detail='food not found')
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(food, k, v)
    db.commit()
    return {'ok': True}


@app.post('/admin/users/{user_id}/restaurants/{restaurant_id}')
def attach_admin(user_id: int, restaurant_id: int, db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail='user not found')
    if not db.get(Restaurant, restaurant_id):
        raise HTTPException(status_code=404, detail='restaurant not found')
    exists = db.scalar(
        select(RestaurantAdmin).where(
            RestaurantAdmin.user_id == user_id,
            RestaurantAdmin.restaurant_id == restaurant_id,
        )
    )
    if exists:
        return {'ok': True}
    admin = RestaurantAdmin(user_id=user_id, restaurant_id=restaurant_id)
    db.add(admin)
    db.commit()
    return {'ok': True}


@app.get('/')
def root():
    return {'service': 'api-service', 'status': 'running'}
