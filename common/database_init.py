"""
Database initialization script.
Creates all tables and types for Main DB and Tracking DB.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy_utils import database_exists, create_database

from .database import (
    MainBase, TrackingBase,
    get_main_engine, get_tracking_engine,
    init_session_factories,
    CuisineType, FoodType, OrderStatus, PaymentMethod
)

def create_enum_types(engine):
    """Create PostgreSQL enum types if they don't exist."""
    with engine.connect() as conn:
        # cuisine_types
        conn.execute(text(f"""
            DO $$ BEGIN
                CREATE TYPE cuisine_types AS ENUM (
                {", ".join(list(map(lambda x: f"'{x}'",CuisineType._value2member_map_.keys())))}
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        
        # food_types
        conn.execute(text(f"""
            DO $$ BEGIN
                CREATE TYPE food_types AS ENUM (
                {", ".join(list(map(lambda x: f"'{x}'",FoodType._value2member_map_.keys())))}
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        
        # order_status
        conn.execute(text(f"""
            DO $$ BEGIN
                CREATE TYPE order_status AS ENUM (
                    {", ".join(list(map(lambda x: f"'{x}'",OrderStatus._value2member_map_.keys())))}
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        
        # payment_methods
        conn.execute(text(f"""
            DO $$ BEGIN
                CREATE TYPE payment_methods AS ENUM ({", ".join(list(map(lambda x: f"'{x}'",PaymentMethod._value2member_map_.keys())))});
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        
        conn.commit()

def create_tracking_enum_types(engine):
    """Create PostgreSQL enum types for tracking DB."""
    with engine.connect() as conn:
        # order_statuses (note: different name from main db)
        conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE order_statuses AS ENUM (
                    'pending', 'confirmed', 'preparing',
                    'delivery', 'finished', 'cancelled'
                );
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        
        # payment_methods
        conn.execute(text(f"""
            DO $$ BEGIN
                CREATE TYPE payment_methods AS ENUM ({", ".join(list(map(lambda x: f"'{x}'",PaymentMethod._value2member_map_.keys())))});
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """))
        
        conn.commit()

def init_main_db(database_url: str = None):
    """Initialize main database with all tables."""
    engine = get_main_engine(database_url)
    
    if not database_exists(engine.url):
        create_database(engine.url)
        print(f"Created database: {engine.url}")
    
    create_enum_types(engine)
    
    # Create all tables
    MainBase.metadata.create_all(bind=engine)
    print("Main DB tables created successfully")
    
    return engine

def init_tracking_db(database_url: str = None):
    """Initialize tracking database with all tables."""
    engine = get_tracking_engine(database_url)
    
    if not database_exists(engine.url):
        create_database(engine.url)
        print(f"Created database: {engine.url}")
    
    create_tracking_enum_types(engine)
    
    # Create all tables
    TrackingBase.metadata.create_all(bind=engine)
    print("Tracking DB tables created successfully")
    
    return engine

def init_all(main_url: str = None, tracking_url: str = None):
    """Initialize both databases."""
    main_engine = init_main_db(main_url)
    tracking_engine = init_tracking_db(tracking_url)
    
    init_session_factories(main_engine, tracking_engine)
    print("All databases initialized and session factories ready")
    
    return main_engine, tracking_engine

if __name__ == "__main__":
    main_url = os.getenv("MAIN_DATABASE_URL", "postgresql://postgres:postgres@main_db:5432/main_db")
    tracking_url = os.getenv("TRACKING_DATABASE_URL", "postgresql://postgres:postgres@tracking_db:5432/tracking_db")
    
    init_all(main_url, tracking_url)
