from __future__ import annotations

import os

from backend.app.shared.config.constants import DEVICE_CLIENT_KEY_ENV_VAR


def get_device_client_key() -> str:
    key = os.getenv(DEVICE_CLIENT_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(f"{DEVICE_CLIENT_KEY_ENV_VAR} is not configured")
    return key

