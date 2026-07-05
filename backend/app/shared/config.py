from __future__ import annotations

import os


def get_device_client_key() -> str:
    key = os.getenv("NOVARIS_DEVICE_CLIENT_KEY")
    if not key:
        raise RuntimeError("NOVARIS_DEVICE_CLIENT_KEY is not configured")
    return key

