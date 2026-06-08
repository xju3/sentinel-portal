"""
Minimal JWT utilities (HS256) without external dependencies.

All config values (secret key, expiry) are passed as parameters rather than
read from a hard-coded config module, so this module is reusable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Dict, Optional


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def create_access_token(
    subject: str,
    tenant_id: str,
    username: str,
    jwt_secret_key: str,
    admin: bool = False,
    contact_id: Optional[str] = None,
    flag: int = 1,
    expires_minutes: int = 1440,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "username": username,
        "admin": admin,
        "contact_id": contact_id,
        "flag": flag,
        "iat": now,
        "exp": now + expires_minutes * 60,
    }

    header_encoded = _b64url_encode(
        json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    payload_encoded = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    signing_input = f"{header_encoded}.{payload_encoded}".encode("ascii")

    signature = hmac.new(
        jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    return f"{header_encoded}.{payload_encoded}.{_b64url_encode(signature)}"


def decode_access_token(token: str, jwt_secret_key: str) -> Dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid token format")

    header_encoded, payload_encoded, signature_encoded = parts
    signing_input = f"{header_encoded}.{payload_encoded}".encode("ascii")
    expected_signature = hmac.new(
        jwt_secret_key.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    token_signature = _b64url_decode(signature_encoded)
    if not hmac.compare_digest(expected_signature, token_signature):
        raise ValueError("invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_encoded).decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive branch
        raise ValueError("invalid token payload") from exc

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp <= int(time.time()):
        raise ValueError("token expired")

    return payload