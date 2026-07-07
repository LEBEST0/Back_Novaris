from collections.abc import Generator
import hashlib
import hmac
import json

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.shared.config.settings import get_behavioural_client_key, get_device_client_key, get_device_signature_secret
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


def require_behavioural_client_key(
    x_novaris_client_key: str | None = Header(default=None, alias="X-Novaris-Client-Key"),
) -> None:
    expected_key = get_behavioural_client_key()
    if not x_novaris_client_key or x_novaris_client_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or missing X-Novaris-Client-Key",
        )


async def require_device_signature(
    request: Request,
    x_novaris_signature: str | None = Header(default=None, alias="X-Novaris-Signature"),
) -> None:
    if not x_novaris_signature:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="missing X-Novaris-Signature",
        )

    body = await request.body()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="empty request body",
        )

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid JSON payload",
        ) from exc

    canonical = json.dumps(parsed, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    expected_signature = hmac.new(
        get_device_signature_secret().encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(x_novaris_signature, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid X-Novaris-Signature",
        )
