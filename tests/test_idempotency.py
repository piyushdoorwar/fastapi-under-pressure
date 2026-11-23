"""Chapter 10 guardrails: sending the same order twice,
with the same Idempotency-Key, makes one order."""

import asyncio

import pytest
from sqlalchemy import func, select
from tests.test_stock import set_stock

from secondloop.db import Session
from secondloop.models import Order


@pytest.fixture(autouse=True)
async def keyboards():
    await set_stock("KBD-MX-R", reno=100)


async def orders_for(email: str) -> int:
    async with Session() as s:
        return await s.scalar(
            select(func.count()).select_from(Order)
            .where(Order.email == email)
        )


def order(email, sku="KBD-MX-R", qty=1):
    return {
        "lines": [{"sku": sku, "qty": qty}],
        "postcode": "94107",
        "email": email,
    }


def key(name):
    return {"Idempotency-Key": f"test-key-{name}"}


def number(resp):
    return resp.json()["number"]


async def test_retry_returns_the_first_order(
    client, inbox
):
    email = "sam@example.com"
    first = await client.post(
        "/orders", json=order(email), headers=key("a")
    )
    again = await client.post(
        "/orders", json=order(email), headers=key("a")
    )
    assert first.status_code == again.status_code == 201
    assert number(again) == number(first)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert await orders_for(email) == 1
    assert len(await inbox.to(email)) == 1


async def test_retry_while_the_first_is_running(
    client, inbox
):
    email = "kim@example.com"
    await inbox.slow(1000)
    first = asyncio.create_task(client.post(
        "/orders", json=order(email), headers=key("b")
    ))
    await asyncio.sleep(0.1)
    again = await client.post(
        "/orders", json=order(email), headers=key("b")
    )
    first = await first
    assert number(again) == number(first)
    assert await orders_for(email) == 1
    assert len(await inbox.to(email)) == 1


async def test_same_key_different_order_is_refused(
    client, inbox
):
    email = "ali@example.com"
    await client.post(
        "/orders", json=order(email), headers=key("c")
    )
    other = await client.post(
        "/orders", json=order(email, qty=2),
        headers=key("c"),
    )
    assert other.status_code == 422
    assert await orders_for(email) == 1


async def test_new_key_is_a_new_order(client, inbox):
    email = "lou@example.com"
    for k in ("d", "e"):
        resp = await client.post(
            "/orders", json=order(email), headers=key(k)
        )
        assert resp.status_code == 201
    assert await orders_for(email) == 2
