"""Security, encryption, and API key management utilities."""

import base64
import hashlib
import secrets
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from app.config import get_settings

KEY_PREFIX = "agb_live_"


def _get_fernet_cipher() -> Fernet:
    """Derive a deterministic 32-byte urlsafe base64 key from BRIDGE_SECRET_KEY."""
    settings = get_settings()
    key_bytes = hashlib.sha256(settings.BRIDGE_SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt a secret string using AES Fernet."""
    if not plain_text:
        return ""
    cipher = _get_fernet_cipher()
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt an encrypted secret string. Returns empty string on failure."""
    if not cipher_text:
        return ""
    try:
        cipher = _get_fernet_cipher()
        return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def generate_api_key() -> Tuple[str, str, str]:
    """
    Generate a new cryptographically secure API key.
    Returns:
        (raw_key, hashed_key, key_prefix)
    The raw_key should be displayed to the user ONCE and never stored.
    """
    token = secrets.token_urlsafe(32)
    raw_key = f"{KEY_PREFIX}{token}"
    hashed_key = hash_api_key(raw_key)
    # Store first 12 characters for display/identification
    prefix_display = raw_key[:14] + "..."
    return raw_key, hashed_key, prefix_display


def hash_api_key(raw_key: str) -> str:
    """Compute SHA-256 hash of the API key for secure database storage."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of a provided API key against the stored hash."""
    if not provided_key or not stored_hash:
        return False
    computed_hash = hash_api_key(provided_key)
    return secrets.compare_digest(computed_hash, stored_hash)
