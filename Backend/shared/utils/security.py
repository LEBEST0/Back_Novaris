"""Hachage du PIN client — jamais stocké en clair (section 18 du cahier des charges Amani
Wallet). PBKDF2-HMAC-SHA256 via la stdlib pour ne pas ajouter de dépendance externe."""

import hashlib
import hmac
import os

_ITERATIONS = 200_000


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERATIONS)
    return hmac.compare_digest(candidate, expected)
