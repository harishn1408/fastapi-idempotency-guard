"""
FastAPI / ASGI Idempotency Middleware.
"""
from __future__ import annotations

from typing import List, Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from fastapi_idempotency_guard.hasher import (
    compute_request_fingerprint,
    verify_fingerprint,
)
from fastapi_idempotency_guard.storage import (
    IdempotencyStatus,
    InMemoryIdempotencyStorage,
)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware enforcing Idempotency-Key headers for mutating HTTP methods (POST, PUT, PATCH).
    """

    def __init__(
        self,
        app,
        storage: Optional[InMemoryIdempotencyStorage] = None,
        header_name: str = "Idempotency-Key",
        enforce_methods: Optional[Set[str]] = None,
        secret: bytes = b"fastapi-idempotency-guard-secret",
    ):
        super().__init__(app)
        self.storage = storage or InMemoryIdempotencyStorage()
        self.header_name = header_name.lower()
        self.enforce_methods = enforce_methods or {"POST", "PUT", "PATCH"}
        self.secret = secret

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in self.enforce_methods:
            return await call_next(request)

        idempotency_key = request.headers.get(self.header_name)
        if not idempotency_key:
            return await call_next(request)

        # Buffer request body for fingerprinting and downstream processing
        body = await request.body()
        fingerprint = compute_request_fingerprint(
            data=body,
            path=request.url.path,
            method=request.method,
            secret=self.secret,
        )

        reserved, record = await self.storage.reserve_or_get(idempotency_key, fingerprint)

        if not reserved and record:
            # Detect payload tampering with the same idempotency key
            if not verify_fingerprint(record.fingerprint, fingerprint):
                return Response(
                    content=b'{"detail":"Idempotency key payload mismatch or tampering detected."}',
                    status_code=409,
                    media_type="application/json",
                )

            if record.status == IdempotencyStatus.IN_PROGRESS:
                return Response(
                    content=b'{"detail":"Concurrent request with the same idempotency key is currently in progress."}',
                    status_code=409,
                    media_type="application/json",
                )

            # Replay cached response
            headers = dict(record.headers or {})
            headers["X-Cache-Lookup"] = "HIT-IDEMPOTENT"
            return Response(
                content=record.body or b"",
                status_code=record.status_code or 200,
                headers=headers,
                media_type=headers.get("content-type", "application/json"),
            )

        # Execute downstream request
        try:
            response = await call_next(request)
            
            # Read response body for caching
            resp_body = [section async for section in response.body_iterator]
            full_resp_body = b"".join(resp_body)

            # Cache successful and client error responses (2xx, 4xx)
            if response.status_code < 500:
                resp_headers = dict(response.headers)
                await self.storage.complete(
                    key=idempotency_key,
                    status_code=response.status_code,
                    headers=resp_headers,
                    body=full_resp_body,
                )
            else:
                # Release on 5xx to allow immediate retry
                await self.storage.release(idempotency_key)

            return Response(
                content=full_resp_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        except Exception:
            await self.storage.release(idempotency_key)
            raise
