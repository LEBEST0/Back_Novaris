from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.shared.database.base import Base

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[4] / "runtime" / "device_intelligence.sqlite3"


def _database_url() -> str:
    default_path = _DEFAULT_DB_PATH.resolve().as_posix()
    return os.getenv("NOVARIS_DATABASE_URL", f"sqlite+pysqlite:///{default_path}")


def _create_engine():
    database_url = _database_url()
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url)


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    from backend.app.modules.device_intelligence import models  # noqa: F401

    if engine.url.drivername.startswith("sqlite") and engine.url.database:
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

