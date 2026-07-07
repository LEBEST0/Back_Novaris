from __future__ import annotations

import os

from backend.app.shared.config.constants import (
    BEHAVIOURAL_CLIENT_KEY_ENV_VAR,
    DEVICE_CLIENT_KEY_ENV_VAR,
    DEVICE_SIGNATURE_SECRET_ENV_VAR,
)


def get_device_client_key() -> str:
    key = os.getenv(DEVICE_CLIENT_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(f"{DEVICE_CLIENT_KEY_ENV_VAR} is not configured")
    return key


def get_device_signature_secret() -> str:
    secret = os.getenv(DEVICE_SIGNATURE_SECRET_ENV_VAR)
    if not secret:
        raise RuntimeError(f"{DEVICE_SIGNATURE_SECRET_ENV_VAR} is not configured")
    return secret


def get_behavioural_client_key() -> str:
    key = os.getenv(BEHAVIOURAL_CLIENT_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(f"{BEHAVIOURAL_CLIENT_KEY_ENV_VAR} is not configured")
    return key
