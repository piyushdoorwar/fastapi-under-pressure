"""Chapter 6 guardrails: checkout keeps working, within
the storefront's time budget, when ParcelPath is slow
or failing, and recovers when ParcelPath does."""

import time

CART = {
    "lines": [{"sku": "LAP-14-R", "qty": 1}],
    "postcode": "94107",
}


async def timed_quote(client):
    start = time.perf_counter()
    resp = await client.post("/checkout/quote", json=CART)
    return resp, time.perf_counter() - start


async def test_healthy_partner_gives_a_real_rate(
    client, partner
):
    resp, _ = await timed_quote(client)
    assert resp.status_code == 200
    assert resp.json()["shipping_estimated"] is False


async def test_quote_survives_a_slow_partner(
    client, partner
):
    await partner(delay_ms=3000)
    resp, seconds = await timed_quote(client)
    assert resp.status_code == 200
    assert resp.json()["shipping_estimated"] is True
    assert seconds < 1.5, f"took {seconds:.3f}s"


async def test_quote_survives_a_failing_partner(
    client, partner
):
    await partner(status=503)
    resp, seconds = await timed_quote(client)
    assert resp.status_code == 200
    assert resp.json()["shipping_estimated"] is True
    assert seconds < 1.5, f"took {seconds:.3f}s"


def test_breaker_opens_then_lets_one_call_through():
    from secondloop.partners.breaker import CircuitBreaker

    now = [0.0]
    breaker = CircuitBreaker(
        failures=3, reset_after_s=10,
        clock=lambda: now[0],
    )
    for _ in range(3):
        assert breaker.allow()
        breaker.record_failure()
    assert breaker.state == "open"
    assert not breaker.allow()

    now[0] = 10.0          # cool-down over
    assert breaker.allow()      # one trial call
    assert not breaker.allow()  # only one
    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.allow()
