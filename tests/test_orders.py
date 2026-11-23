"""Chapter 8 guardrails: an order the customer is told
about exists, and an order that can't be saved is
never announced."""

from sqlalchemy import func, select

from secondloop.db import Session
from secondloop.models import Order, StockLevel


async def stock_of(sku: str) -> int:
    async with Session() as s:
        return await s.scalar(
            select(func.sum(StockLevel.qty))
            .where(StockLevel.sku == sku)
        )


async def order_count(email: str) -> int:
    async with Session() as s:
        return await s.scalar(
            select(func.count()).select_from(Order)
            .where(Order.email == email)
        )


def order(email, sku, qty):
    return {
        "lines": [{"sku": sku, "qty": qty}],
        "postcode": "94107",
        "email": email,
    }


async def test_order_is_saved_and_confirmed(
    client, inbox
):
    email = "ana@example.com"
    resp = await client.post(
        "/orders", json=order(email, "LAP-14-R", 1)
    )
    assert resp.status_code == 201
    number = resp.json()["number"]
    assert await order_count(email) == 1
    [message] = await inbox.to(email)
    assert number in message["subject"]


async def test_too_many_is_refused_quietly(client, inbox):
    email = "dana@example.com"
    left = await stock_of("PHN-12-R")
    resp = await client.post(
        "/orders", json=order(email, "PHN-12-R", left + 1)
    )
    assert resp.status_code == 409
    assert await order_count(email) == 0
    assert await inbox.to(email) == []
    assert await stock_of("PHN-12-R") == left


async def test_email_failure_keeps_the_order(
    client, inbox
):
    email = "lee@example.com"
    await inbox.fail_with(503)
    resp = await client.post(
        "/orders", json=order(email, "CHG-65-C", 1)
    )
    assert resp.status_code == 201
    assert resp.json()["confirmation_sent"] is False
    assert await order_count(email) == 1
