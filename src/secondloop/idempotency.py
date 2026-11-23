"""Idempotency keys for POST /orders.

The storefront sends an Idempotency-Key header with
every order, the same key on every retry. The first
request with a key claims it, in the same transaction
that saves the order. Any later request with that key
gets the same order back instead of a new one.
"""

import hashlib

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from secondloop.models import IdempotencyKey, Order


def fingerprint(body: BaseModel) -> str:
    data = body.model_dump_json().encode()
    return hashlib.sha256(data).hexdigest()


async def claim(db, key: str, digest: str) -> bool:
    """Insert the key. Return False if another request
    already committed it. If that request's transaction
    is still open, PostgreSQL makes this wait for it."""
    claimed = await db.scalar(
        insert(IdempotencyKey)
        .values(key=key, request_hash=digest)
        .on_conflict_do_nothing()
        .returning(IdempotencyKey.key)
    )
    return claimed is not None


async def link(db, key: str, order: Order) -> None:
    await db.flush()  # gives the order its id
    await db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.key == key)
        .values(order_id=order.id)
    )


async def find(db, key: str, digest: str) -> Order | None:
    """The order this key made, if it made one."""
    row = await db.get(IdempotencyKey, key)
    if row is None:
        return None
    if row.request_hash != digest:
        raise HTTPException(
            422,
            "Idempotency-Key was already used for a"
            " different order",
        )
    return await db.get(Order, row.order_id)
