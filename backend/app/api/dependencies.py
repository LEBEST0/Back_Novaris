from collections.abc import Generator

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.shared.config import get_device_client_key
from backend.app.shared.database.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_device_client_key(
    x_novaris_client_key: str | None = Header(default=None, alias="X-Novaris-Client-Key"),
) -> None:
    expected_key = get_device_client_key()
    if not x_novaris_client_key or x_novaris_client_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or missing X-Novaris-Client-Key",
        )
