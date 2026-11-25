"""Chapter 13 guardrails: each confirmation is
delivered once, however the worker fails."""

import asyncio

import pytest
from sqlalchemy import delete, select, update
from tests.test_stock import set_stock

from secondloop.db import Session
from secondloop.models import Order, OutboxMessage
from secondloop.outbox import deliver_pending
from secondloop.partners.mailer import (
    Mailer,
    make_mailer_http,
)


@pytest.fixture(autouse=True)
async def keyboards():
    await set_stock("KBD-MX-R", reno=100)


@pytest.fixture
async def mailer():
    async with make_mailer_http() as http:
        yield Mailer(http)


class StuckMailer(Mailer):
    """A worker that has stopped: paused, swapping,
    or waiting on a connection that will never answer."""

    async def send(self, *args, **kwargs):
        await asyncio.Event().wait()


async def place(client, email):
    resp = await client.post("/orders", json={
        "lines": [{"sku": "KBD-MX-R", "qty": 1}],
        "postcode": "94107",
        "email": email,
    })
    assert resp.status_code == 201


async def message_for(email) -> OutboxMessage:
    async with Session() as s:
        return await s.scalar(
            select(OutboxMessage)
            .join(Order).where(Order.email == email)
        )


async def make_due(msg):
    async with Session.begin() as s:
        await s.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == msg.id)
            .values(available_at=msg.created_at)
        )


async def test_slow_provider_sends_once(
    client, inbox, mailer
):
    email = "wes@example.com"
    await deliver_pending(mailer)  # anything left over
    await place(client, email)
    await inbox.slow(400)  # longer than our timeout
    assert await deliver_pending(mailer) == 0
    await inbox.slow(0)
    await make_due(await message_for(email))
    assert await deliver_pending(mailer) == 1
    await asyncio.sleep(0.5)  # the slow one lands
    assert len(await inbox.to(email)) == 1


async def test_stuck_worker_lets_go(
    client, inbox, mailer
):
    email = "xia@example.com"
    await deliver_pending(mailer)
    await place(client, email)
    async with make_mailer_http() as http:
        stuck = asyncio.create_task(
            deliver_pending(StuckMailer(http))
        )
        await asyncio.sleep(0.8)  # past the lease
        try:
            assert await deliver_pending(mailer) == 1
        finally:
            stuck.cancel()
    assert len(await inbox.to(email)) == 1


async def test_undeliverable_address_is_set_aside(
    client, inbox, mailer
):
    bad, good = "yan@example", "zoe@example.com"
    await deliver_pending(mailer)
    await place(client, bad)
    await place(client, good)
    msg = await message_for(bad)
    try:
        assert await deliver_pending(mailer) == 1
        assert len(await inbox.to(good)) == 1
        msg = await message_for(bad)
        assert msg.dead_at is not None
        assert msg.sent_at is None
    finally:  # don't leave it to block other tests
        async with Session.begin() as s:
            await s.execute(
                delete(OutboxMessage)
                .where(OutboxMessage.id == msg.id)
            )
