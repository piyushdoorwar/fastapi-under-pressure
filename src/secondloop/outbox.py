"""The order confirmation outbox.

The order handler adds a row to `outbox` in the same
transaction as the order, so an order and its email are
saved together or not at all. A separate process, the
worker (secondloop.worker), sends what's waiting.

Delivery is at least once (chapter 13):

- A worker leases a message for a short time, commits,
  and sends with no transaction open. If the worker
  dies or hangs, the lease runs out and another worker
  takes the message.
- Every attempt sends the same Idempotency-Key, so the
  provider sends each message once however many times
  it is asked.
- A message the provider refuses outright, or that has
  failed too often, becomes a dead letter for a person
  to look at, instead of being tried for ever.
"""

import datetime as dt
from dataclasses import dataclass

import structlog
from sqlalchemy import delete, func, or_, select, update

from secondloop.db import Session
from secondloop.models import IdempotencyKey, Order
from secondloop.models import OutboxMessage as Message
from secondloop.partners.mailer import Mailer, MailerError
from secondloop.settings import settings

log = structlog.get_logger()
MAX_DELAY = dt.timedelta(minutes=5)
KEEP_KEYS = dt.timedelta(hours=24)


def queue_confirmation(db, order: Order) -> None:
    """Call inside the order's transaction."""
    db.add(Message(order_id=order.id))


def retry_delay(attempts: int) -> dt.timedelta:
    """1 s, 2 s, 4 s ... up to five minutes."""
    return min(dt.timedelta(seconds=2 ** (attempts - 1)),
               MAX_DELAY)


@dataclass
class Claim:
    id: int
    order_id: int
    attempts: int
    email: str
    number: str


async def claim_next() -> Claim | None:
    """Lease the oldest message that is due and not
    leased by a live worker, in a short transaction."""
    lease = dt.timedelta(seconds=settings.outbox_lease_s)
    due = (
        select(Message.id)
        .where(Message.sent_at.is_(None),
               Message.dead_at.is_(None),
               Message.available_at <= func.now(),
               or_(Message.leased_until.is_(None),
                   Message.leased_until < func.now()))
        .order_by(Message.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    async with Session.begin() as db:
        row = (await db.execute(
            update(Message)
            .where(Message.id == due)
            .values(leased_until=func.now() + lease,
                    attempts=Message.attempts + 1)
            .returning(Message.id, Message.order_id,
                       Message.attempts)
        )).first()
        if row is None:
            return None
        order = await db.get(Order, row.order_id)
        return Claim(row.id, row.order_id, row.attempts,
                     order.email, order.number)


async def deliver_one(mailer: Mailer) -> str | None:
    """Send one message. Return "sent", "retry" or
    "dead", or None if nothing was waiting."""
    claim = await claim_next()
    if claim is None:
        return None
    number = claim.number
    try:
        await mailer.send(
            claim.email,
            f"Your SecondLoop order {number}",
            f"Thanks! We've received order {number}.",
            key=f"outbox-{claim.id}",
        )
    except MailerError as exc:
        return await failed(claim, exc)
    await sent(claim)
    return "sent"


async def sent(claim: Claim) -> None:
    async with Session.begin() as db:
        await db.execute(
            update(Message)
            .where(Message.id == claim.id)
            .values(sent_at=func.now(), leased_until=None)
        )
        await db.execute(
            update(Order)
            .where(Order.id == claim.order_id)
            .values(confirmation_sent_at=func.now())
        )
    log.info("confirmation_sent", order=claim.number)


async def failed(claim: Claim, exc: MailerError) -> str:
    dead = (exc.permanent or claim.attempts
            >= settings.outbox_max_attempts)
    later = func.now() + retry_delay(claim.attempts)
    async with Session.begin() as db:
        await db.execute(
            update(Message)
            .where(Message.id == claim.id,
                   Message.sent_at.is_(None))
            .values(
                last_error=str(exc)[:200],
                leased_until=None,
                available_at=later,
                dead_at=func.now() if dead else None,
            )
        )
    event = "confirmation_dead" if dead else (
        "confirmation_retry_later")
    log.warning(event, order=claim.number,
                attempts=claim.attempts, error=str(exc))
    return "dead" if dead else "retry"


async def deliver_pending(mailer, stop=None) -> int:
    """Send everything that is due; return how many were
    sent. Stops early when `stop` is set, or when the
    provider is struggling."""
    sent_count = 0
    while stop is None or not stop.is_set():
        result = await deliver_one(mailer)
        if result is None or result == "retry":
            break
        sent_count += result == "sent"
    return sent_count


async def revive(message_id: int) -> bool:
    """Put a dead letter back in the queue, after a
    person has fixed what was wrong."""
    async with Session.begin() as db:
        result = await db.execute(
            update(Message)
            .where(Message.id == message_id,
                   Message.dead_at.is_not(None))
            .values(dead_at=None, attempts=0,
                    available_at=func.now())
        )
    return result.rowcount == 1


async def forget_old_keys() -> int:
    """Idempotency keys only need to outlive a client's
    retries (chapter 10)."""
    async with Session.begin() as db:
        result = await db.execute(
            delete(IdempotencyKey).where(
                IdempotencyKey.created_at
                < func.now() - KEEP_KEYS
            )
        )
    return result.rowcount
