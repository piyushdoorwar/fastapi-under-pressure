"""Chapter 4 guardrails: the database pool must not
be held hostage by a slow partner, and a full pool
must fail fast instead of queueing for 30 seconds."""

import asyncio
import time
from contextlib import AsyncExitStack

from secondloop.db import engine

CART = {
    "lines": [{"sku": "LAP-14-R", "qty": 1}],
    "postcode": "94107",
}


async def timed_get(client, path, delay=0.1):
    await asyncio.sleep(delay)  # let the quotes start
    start = time.perf_counter()
    resp = await client.get(path)
    return resp, time.perf_counter() - start


async def test_quotes_do_not_starve_the_pool(
    client, slow_partner
):
    more_than_pool = engine.sync_engine.pool.size() + 2
    quotes = [
        client.post("/checkout/quote", json=CART)
        for _ in range(more_than_pool)
    ]
    *answers, (resp, seconds) = await asyncio.gather(
        *quotes, timed_get(client, "/products")
    )
    assert all(a.status_code == 200 for a in answers)
    assert resp.status_code == 200
    assert seconds < 0.15, f"took {seconds:.3f}s"


async def test_full_pool_fails_fast(client):
    size = engine.sync_engine.pool.size()
    async with AsyncExitStack() as stack:
        for _ in range(size):  # take every connection
            await stack.enter_async_context(
                engine.connect()
            )
        start = time.perf_counter()
        async with asyncio.timeout(5):
            resp = await client.get("/products")
        seconds = time.perf_counter() - start
    assert resp.status_code == 503
    assert resp.headers["retry-after"] == "1"
    assert seconds < 1.5, f"took {seconds:.3f}s"
