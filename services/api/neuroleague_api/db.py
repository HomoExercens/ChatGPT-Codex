from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from neuroleague_api.core.config import Settings


class Base(DeclarativeBase):
    pass


settings = Settings()
engine = create_engine(settings.db_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
