# fastapi-idempotency-guard

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Tests: Passing](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

Production ASGI & FastAPI idempotency middleware designed to eliminate duplicate webhook executions, double-charges, and distributed zombie locks:
- **Keyed HMAC-SHA256 Fingerprinting**: Canonical payload serialization detecting client-side request tampering.
- **Sensitive Field Redaction**: Automatically redacts passwords, tokens, API keys, and CVVs before calculating request digests.
- **Zombie-Lock TTL Recovery**: Automatically recovers when worker nodes crash mid-transaction without releasing leases.
- **Zero Double Executions**: Concurrency stress-tested under burst asynchronous loads.

---

## Quickstart

```python
from fastapi import FastAPI
from fastapi_idempotency_guard import IdempotencyMiddleware, InMemoryIdempotencyStorage

app = FastAPI()
storage = InMemoryIdempotencyStorage(zombie_lock_seconds=60.0)

app.add_middleware(
    IdempotencyMiddleware,
    storage=storage,
    header_name="Idempotency-Key"
)

@app.post("/checkout")
async def checkout(order: OrderRequest):
    # Safe from concurrent double executions
    return process_order(order)
```

---

## Concurrency Verification

Tested with `asyncio.gather` across 100 simultaneous concurrent requests:
```
100 Concurrent Requests -> Exactly 1 Execution + 99 Replays (`X-Cache-Lookup: HIT-IDEMPOTENT`)
```

---

## License

MIT &copy; 2026 Harish Nair
