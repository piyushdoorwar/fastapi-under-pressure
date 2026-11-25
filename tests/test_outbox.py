"""Chapter 12 guardrails: a confirmation is saved with
its order, and sent by the worker, once."""

import pytest
from sqlalchemy import select, update
from tests.test_stock import set_stock

from secondloop.db import Session
from secondloop.models import Order
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


async def place(client, email, qty=1):
    return await client.post("/orders", json={
        "lines": [{"sku": "KBD-MX-R", "qty": qty}],
        "postcode": "94107",
        "email": email,
    })


async def messages_for(email):
    from secondloop.models import OutboxMessage

    async with Session() as s:
        return list(await s.scalars(
            select(OutboxMessage)
            .join(Order).where(Order.email == email)
        ))


async def test_order_queues_its_confirmation(
    client, inbox
):
    resp = await place(client, "ola@example.com")
    assert resp.status_code == 201
    [msg] = await messages_for("ola@example.com")
    assert msg.sent_at is None


async def test_refused_order_queues_nothing(
    client, inbox
):
    await set_stock("KBD-MX-R", reno=1)
    resp = await place(client, "rex@example.com", 2)
    assert resp.status_code == 409
    assert await messages_for("rex@example.com") == []


async def test_worker_sends_each_one_once(
    client, inbox, mailer
):
    from secondloop.outbox import deliver_pending

    email = "uma@example.com"
    await place(client, email)
    assert await deliver_pending(mailer) >= 1
    assert await deliver_pending(mailer) == 0
    assert len(await inbox.to(email)) == 1
    [msg] = await messages_for(email)
    assert msg.sent_at is not None


async def test_failed_send_is_tried_again_later(
    client, inbox, mailer
):
    from secondloop.outbox import deliver_pending

    from secondloop.models import OutboxMessage

    email = "vic@example.com"
    await place(client, email)
    await deliver_pending(mailer)  # anything left over
    await place(client, email)
    await inbox.fail_with(503)
    assert await deliver_pending(mailer) == 0
    await inbox.fail_with(202)
    assert await deliver_pending(mailer) == 0  # not due
    [_, msg] = await messages_for(email)
    assert msg.attempts == 1 and msg.sent_at is None

    async with Session.begin() as s:  # make it due now
        await s.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == msg.id)
            .values(available_at=msg.created_at)
        )
    assert await deliver_pending(mailer) == 1
    assert len(await inbox.to(email)) == 2
