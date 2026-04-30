from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

import time

Base = declarative_base()


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def wait_for_database(engine, retries: int = 30, delay: float = 2.0) -> None:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
                return
        except Exception as exc:  # pragma: no cover
            last_exc = exc
            time.sleep(delay)
    if last_exc:
        raise last_exc
