import asyncio
import pytest
from fastapi_idempotency_guard.storage import (
    IdempotencyStatus,
    InMemoryIdempotencyStorage,
)

@pytest.mark.anyio
async def test_atomic_reservation_and_completion():
    storage = InMemoryIdempotencyStorage()
    key = "order-tx-1001"
    fp = "hash123"

    # First attempt: successfully reserved
    res, rec = await storage.reserve_or_get(key, fp)
    assert res is True
    assert rec is None

    # Immediate duplicate while IN_PROGRESS: rejected
    res2, rec2 = await storage.reserve_or_get(key, fp)
    assert res2 is False
    assert rec2.status == IdempotencyStatus.IN_PROGRESS

    # Complete the request
    await storage.complete(key, status_code=201, headers={"content-type": "application/json"}, body=b'{"id":"order_1"}')

    # Subsequent request: returns completed record for replay
    res3, rec3 = await storage.reserve_or_get(key, fp)
    assert res3 is False
    assert rec3.status == IdempotencyStatus.COMPLETED
    assert rec3.body == b'{"id":"order_1"}'

@pytest.mark.anyio
async def test_zombie_lock_recovery():
    storage = InMemoryIdempotencyStorage(zombie_lock_seconds=0.1)
    key = "zombie-tx-999"

    # Reserve key
    res, _ = await storage.reserve_or_get(key, "fp_old")
    assert res is True

    # Wait past zombie lock timeout
    await asyncio.sleep(0.15)

    # Next attempt steals the zombie lock
    res2, _ = await storage.reserve_or_get(key, "fp_new")
    assert res2 is True
