"""Helper utilities for encrypting and decrypting sensitive account credentials."""

from __future__ import annotations

import base64
import hashlib
import string
from functools import lru_cache
from typing import Optional

from flask import current_app
from cryptography.fernet import Fernet, InvalidToken


def _normalize_key(raw_key: Optional[str]) -> bytes:
    """Derive a valid Fernet key from configuration or fallback secret."""
    if raw_key:
        if isinstance(raw_key, bytes):
            key_bytes = raw_key
        else:
            key_bytes = raw_key.encode("utf-8")
        try:
            base64.urlsafe_b64decode(key_bytes)
            return key_bytes
        except Exception:
            return base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
    secret = current_app.config.get("SECRET_KEY", "dev-secret-key")
    if isinstance(secret, bytes):
        secret_bytes = secret
    else:
        secret_bytes = str(secret).encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(secret_bytes).digest())


@lru_cache(maxsize=2)
def _get_cipher(key_identifier: Optional[str]) -> Fernet:
    """Return cached Fernet cipher derived from configuration."""
    key = _normalize_key(key_identifier)
    return Fernet(key)


def _current_cipher() -> Fernet:
    """Helper to obtain a Fernet cipher using configured key."""
    key_identifier = current_app.config.get("ACCOUNTS_ENCRYPTION_KEY")
    return _get_cipher(key_identifier)


def encrypt_value(value: str) -> str:
    """Encrypt the provided value using Fernet symmetric encryption."""
    if not value:
        return ""
    cipher = _current_cipher()
    token = cipher.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(value: str) -> str:
    """Decrypt a previously encrypted value.

    Falls back to returning the original value when decryption is not possible
    (e.g., legacy plaintext or hashed values).
    """
    if not value:
        return ""
    cipher = _current_cipher()
    try:
        return cipher.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return value


def is_likely_legacy_hash(value: str) -> bool:
    """Return True when the value looks like a legacy SHA256 hex digest."""
    if not value:
        return False
    value = value.strip()
    return len(value) == 64 and all(ch in string.hexdigits for ch in value)
