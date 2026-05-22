"""Password auth helpers — PBKDF2-SHA256, 200k iterations, per-user salt.
Operates on a plain dict (the user's `config` JSONB). Matches the upstream
user-management hash shape so credentials are shared across services."""
from __future__ import annotations

import hashlib
import hmac
import secrets

WEB_PASSWORD_HASH_KEY = "web_password_hash"
WEB_PASSWORD_SALT_KEY = "web_password_salt"
PBKDF2_ITERATIONS = 200_000


def has_web_password(config: dict) -> bool:
    return bool(config.get(WEB_PASSWORD_HASH_KEY) and config.get(WEB_PASSWORD_SALT_KEY))


def _pbkdf2(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex()


def set_web_password(config: dict, password: str) -> None:
    salt_hex = secrets.token_hex(16)
    config[WEB_PASSWORD_SALT_KEY] = salt_hex
    config[WEB_PASSWORD_HASH_KEY] = _pbkdf2(password, salt_hex)


def verify_web_password(config: dict, password: str) -> bool:
    stored_hash = config.get(WEB_PASSWORD_HASH_KEY)
    stored_salt = config.get(WEB_PASSWORD_SALT_KEY)
    if not stored_hash or not stored_salt:
        return False
    candidate = _pbkdf2(password, stored_salt)
    return hmac.compare_digest(candidate, stored_hash)
