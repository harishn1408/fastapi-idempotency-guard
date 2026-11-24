"""
HMAC-SHA256 request payload canonicalization and fingerprinting.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Set

SENSITIVE_FIELDS: Set[str] = {
    "password", "token", "secret", "access_token", "credit_card",
    "authorization", "api_key", "refresh_token", "otp", "cvv"
}


def sanitize_payload(obj: Any) -> Any:
    """Recursively redacts sensitive keys from payload structures before hashing."""
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() in SENSITIVE_FIELDS else sanitize_payload(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [sanitize_payload(item) for item in obj]
    return obj


def compute_request_fingerprint(
    data: Any,
    path: str = "",
    method: str = "POST",
    secret: bytes = b"idempotency-default-secret"
) -> str:
    """
    Computes a canonical HMAC-SHA256 digest over the HTTP method, path, and sanitized JSON payload.
    Ensures identical requests yield identical fingerprints while detecting payload tampering.
    """
    if isinstance(data, (bytes, bytearray)):
        try:
            parsed = json.loads(data.decode("utf-8"))
            body_bytes = json.dumps(sanitize_payload(parsed), sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:
            body_bytes = bytes(data)
    elif isinstance(data, str):
        try:
            parsed = json.loads(data)
            body_bytes = json.dumps(sanitize_payload(parsed), sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:
            body_bytes = data.encode("utf-8")
    elif data is None:
        body_bytes = b""
    else:
        body_bytes = json.dumps(sanitize_payload(data), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    message = b"|".join([
        method.upper().encode("utf-8"),
        path.encode("utf-8"),
        body_bytes
    ])

    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_fingerprint(stored_fingerprint: str, current_fingerprint: str) -> bool:
    """Constant-time comparison preventing timing attack vectors."""
    return hmac.compare_digest(stored_fingerprint, current_fingerprint)
