import asyncio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from fastapi_idempotency_guard.middleware import IdempotencyMiddleware
from fastapi_idempotency_guard.storage import InMemoryIdempotencyStorage

app = FastAPI()
storage = InMemoryIdempotencyStorage()
app.add_middleware(IdempotencyMiddleware, storage=storage)

execution_counter = 0

@app.post("/payments/charge")
async def charge_payment():
    global execution_counter
    await asyncio.sleep(0.05)  # simulate db transaction
    execution_counter += 1
    return {"status": "paid", "counter": execution_counter}

@pytest.mark.anyio
async def test_100_concurrent_requests_zero_duplicate_executions():
    global execution_counter
    execution_counter = 0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First request to establish completed record
        res0 = await client.post(
            "/payments/charge",
            headers={"Idempotency-Key": "concurrent-burst-key"},
            json={"amount": 100}
        )
        assert res0.status_code == 200
        assert res0.json()["counter"] == 1

        # Now send 99 concurrent requests with identical key
        async def send_req():
            return await client.post(
                "/payments/charge",
                headers={"Idempotency-Key": "concurrent-burst-key"},
                json={"amount": 100}
            )

        responses = await asyncio.gather(*(send_req() for _ in range(99)))

        for r in responses:
            assert r.status_code == 200
            assert r.json()["counter"] == 1
            assert r.headers.get("x-cache-lookup") == "HIT-IDEMPOTENT"

        # Under 100 total requests, the underlying payment handler was executed EXACTLY ONCE
        assert execution_counter == 1
