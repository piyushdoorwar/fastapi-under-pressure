"""Chapter 3 guardrail: a slow shipping partner must
not slow down requests that never call it."""

import asyncio
import time

CART = {
    "lines": [{"sku": "LAP-14-R", "qty": 1}],
    "postcode": "94107",
}


async def timed_get(client, path):
    await asyncio.sleep(0.05)  # let the quotes start
    start = time.perf_counter()
    resp = await client.get(path)
    return resp, time.perf_counter() - start


async def test_catalogue_stays_fast(client, slow_partner):
    quotes = [
        client.post("/checkout/quote", json=CART)
        for _ in range(5)
    ]
    *answers, (resp, seconds) = await asyncio.gather(
        *quotes, timed_get(client, "/products")
    )
    assert all(a.status_code == 200 for a in answers)
    assert resp.status_code == 200
    assert seconds < 0.15, f"took {seconds:.3f}s"
