"""Look at the outbox, and put dead letters back.

    python tools/outbox.py              # what's waiting
    python tools/outbox.py --dead       # dead letters
    python tools/outbox.py --revive 42  # try 42 again
"""

import argparse
import asyncio

from sqlalchemy import select

from secondloop.db import Session
from secondloop.models import Order, OutboxMessage
from secondloop.outbox import revive


async def show(dead: bool) -> None:
    m = OutboxMessage
    query = (
        select(m.id, Order.number, Order.email,
               m.attempts, m.last_error)
        .join(Order)
        .where(m.sent_at.is_(None))
        .where(m.dead_at.is_not(None) if dead
               else m.dead_at.is_(None))
        .order_by(m.id)
    )
    async with Session() as s:
        for row in await s.execute(query):
            print(" ".join(str(v) for v in row))


async def main(args):
    if args.revive:
        ok = await revive(args.revive)
        print("revived" if ok else "not a dead letter")
    else:
        await show(args.dead)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dead", action="store_true")
    parser.add_argument("--revive", type=int)
    asyncio.run(main(parser.parse_args()))
