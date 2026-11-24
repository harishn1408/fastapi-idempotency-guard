import pytest
from fastapi_idempotency_guard.hasher import (
    compute_request_fingerprint,
    sanitize_payload,
    verify_fingerprint,
)

def test_fingerprint_deterministic_and_canonical():
    payload_a = {"user_id": 101, "amount": 500.0, "currency": "USD"}
    payload_b = {"currency": "USD", "amount": 500.0, "user_id": 101}

    fp_a = compute_request_fingerprint(payload_a, path="/v1/charge", method="POST")
    fp_b = compute_request_fingerprint(payload_b, path="/v1/charge", method="POST")

    assert fp_a == fp_b
    assert verify_fingerprint(fp_a, fp_b) is True

def test_tampering_detection():
    payload_original = {"amount": 500.0}
    payload_tampered = {"amount": 5000.0}

    fp_orig = compute_request_fingerprint(payload_original, path="/v1/charge")
    fp_tamp = compute_request_fingerprint(payload_tampered, path="/v1/charge")

    assert fp_orig != fp_tamp
    assert verify_fingerprint(fp_orig, fp_tamp) is False

def test_sensitive_field_redaction():
    payload = {"card_number": "1234-5678", "cvv": "123", "password": "supersecret"}
    sanitized = sanitize_payload(payload)

    assert sanitized["cvv"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["card_number"] == "1234-5678"
