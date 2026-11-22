import asyncio
import time

from secondloop.observability import (
    LOOP_LAG,
    watch_event_loop,
)


async def test_request_id_is_echoed(client):
    resp = await client.get(
        "/products", headers={"x-request-id": "abc123"}
    )
    assert resp.headers["x-request-id"] == "abc123"


async def test_metrics_use_route_templates(client):
    await client.get("/products/LAP-14-R")
    resp = await client.get("/metrics")
    assert 'route="/products/{sku}"' in resp.text


async def test_lag_monitor_sees_a_blocked_loop():
    watcher = asyncio.create_task(watch_event_loop())
    await asyncio.sleep(0.06)   # let it start ticking
    time.sleep(0.3)  # noqa: ASYNC251 (blocks on purpose)
    await asyncio.sleep(0.01)   # let it wake and measure
    watcher.cancel()
    assert LOOP_LAG._value.get() > 0.2
