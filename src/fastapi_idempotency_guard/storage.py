"""
Storage backend with atomic leases, cached response persistence, and zombie-lock recovery.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import time
from typing import Dict, Optional, Tuple


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


@dataclass
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: IdempotencyStatus
    created_at: float
    status_code: Optional[int] = None
    headers: Optional[Dict[str, str]] = None
    body: Optional[bytes] = None


class InMemoryIdempotencyStorage:
    """
    Thread/async-safe in-memory idempotency storage supporting atomic lock acquisition,
    zombie-lock recovery after unhandled worker crashes, and response caching.
    """

    def __init__(self, zombie_lock_seconds: float = 120.0, ttl_seconds: float = 86400.0):
        self.zombie_lock_seconds = zombie_lock_seconds
        self.ttl_seconds = ttl_seconds
        self._records: Dict[str, IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    async def reserve_or_get(
        self, key: str, fingerprint: str
    ) -> Tuple[bool, Optional[IdempotencyRecord]]:
        """
        Attempts to reserve an idempotency key.
        Returns:
            (True, None) -> Key reserved successfully. Caller must proceed with request.
            (False, record) -> Key already exists.
                               If record.status == COMPLETED: replay cached response.
                               If record.status == IN_PROGRESS: concurrent execution in flight.
        """
        async with self._lock:
            now = time.monotonic()
            record = self._records.get(key)

            if record is not None:
                # Check for zombie lock
                if (
                    record.status == IdempotencyStatus.IN_PROGRESS
                    and (now - record.created_at) > self.zombie_lock_seconds
                ):
                    # Zombie lock timed out; steal reservation
                    new_record = IdempotencyRecord(
                        key=key,
                        fingerprint=fingerprint,
                        status=IdempotencyStatus.IN_PROGRESS,
                        created_at=now,
                    )
                    self._records[key] = new_record
                    return True, None

                return False, record

            # Key is available; reserve atomically
            new_record = IdempotencyRecord(
                key=key,
                fingerprint=fingerprint,
                status=IdempotencyStatus.IN_PROGRESS,
                created_at=now,
            )
            self._records[key] = new_record
            return True, None

    async def complete(
        self, key: str, status_code: int, headers: Dict[str, str], body: bytes
    ) -> None:
        """Stores the completed HTTP response for replay on duplicate requests."""
        async with self._lock:
            record = self._records.get(key)
            if record:
                record.status = IdempotencyStatus.COMPLETED
                record.status_code = status_code
                record.headers = headers
                record.body = body

    async def release(self, key: str) -> None:
        """Releases the reservation upon server error to allow subsequent retries."""
        async with self._lock:
            self._records.pop(key, None)
