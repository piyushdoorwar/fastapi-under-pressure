"""The order confirmation outbox.

The order handler adds a row to `outbox` in the same
transaction as the order, so an order and its email are
saved together or not at all. A separate process, the
worker (secondloop.worker), sends what's waiting.
"""

import datetime as dt

import structlog
from sqlalchemy import delete, func, select

from secondloop.db import Session
from secondloop.models import IdempotencyKey, Order
from secondloop.models import OutboxMessage as Message
from secondloop.partners.mailer import Mailer, MailerError

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


async def deliver_one(mailer: Mailer) -> bool | None:
    """Send the oldest message that is due. Return True
    if it was sent, False if sending failed, or None if
    nothing was waiting."""
    async with Session.begin() as db:
        msg = await db.scalar(
            select(Message)
            .where(Message.sent_at.is_(None),
                   Message.available_at <= func.now())
            .order_by(Message.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if msg is None:
            return None
        order = await db.get(Order, msg.order_id)
        try:
            await mailer.send(
                order.email,
                f"Your SecondLoop order {order.number}",
                "Thanks! We've received order"
                f" {order.number}.",
            )
        except MailerError as exc:
            # The row is locked, so this read-then-write
            # is safe (chapter 9).
            msg.attempts += 1
            msg.last_error = str(exc)[:200]
            msg.available_at = (
                func.now() + retry_delay(msg.attempts)
            )
            log.warning("confirmation_retry_later",
                        order=order.number,
                        attempts=msg.attempts)
            return False
        msg.sent_at = func.now()
        order.confirmation_sent_at = func.now()
        log.info("confirmation_sent", order=order.number)
        return True


async def deliver_pending(mailer, stop=None) -> int:
    """Send everything that is due; return how many were
    sent. Stops early when `stop` is set."""
    sent = 0
    while stop is None or not stop.is_set():
        result = await deliver_one(mailer)
        if result is None:
            break
        sent += bool(result)
        if result is False:
            break  # the provider is struggling; back off
    return sent


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
