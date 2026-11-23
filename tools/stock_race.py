"""Five ways to take the last unit, side by side.

    python tools/stock_race.py --buyers 8 --stock 1

Each buyer opens its own connection and transaction,
tries to take one TAB-10-R from Dallas, and pauses
50 ms between reading and writing (the time a real
request spends doing other work). The script resets
the stock before each strategy and prints how many
units were sold and what the losers saw.
"""

import argparse
import asyncio
import os
import time
from collections import Counter

import asyncpg

DSN = os.getenv(
    "PG_DSN", "postgresql://postgres@localhost/secondloop"
)
SKU, WAREHOUSE = "TAB-10-R", "dallas"
WHERE = "sku = $1 and warehouse = $2"
PAUSE = 0.05


async def read_then_write(tx):
    qty = await tx.fetchval(
        f"select qty from stock_levels where {WHERE}",
        SKU, WAREHOUSE)
    if qty < 1:
        return "409"
    await asyncio.sleep(PAUSE)
    await tx.execute(
        f"update stock_levels set qty = $3 where {WHERE}",
        SKU, WAREHOUSE, qty - 1)
    return "sold"


async def relative_write(tx):
    qty = await tx.fetchval(
        f"select qty from stock_levels where {WHERE}",
        SKU, WAREHOUSE)
    if qty < 1:
        return "409"
    await asyncio.sleep(PAUSE)
    await tx.execute(
        "update stock_levels set qty = qty - 1"
        f" where {WHERE}", SKU, WAREHOUSE)
    return "sold"


async def for_update(tx):
    qty = await tx.fetchval(
        f"select qty from stock_levels where {WHERE}"
        " for update", SKU, WAREHOUSE)
    if qty < 1:
        return "409"
    await asyncio.sleep(PAUSE)
    await tx.execute(
        "update stock_levels set qty = qty - 1"
        f" where {WHERE}", SKU, WAREHOUSE)
    return "sold"


async def conditional(tx):
    await asyncio.sleep(PAUSE)
    row = await tx.fetchrow(
        "update stock_levels set qty = qty - 1"
        f" where {WHERE} and qty >= 1 returning qty",
        SKU, WAREHOUSE)
    return "sold" if row else "409"


STRATEGIES = {
    "read, then write the number": (
        read_then_write, "read_committed"),
    "read, then write qty - 1": (
        relative_write, "read_committed"),
    "select ... for update": (
        for_update, "read_committed"),
    "update ... where qty >= 1": (
        conditional, "read_committed"),
    "serializable, read then write": (
        read_then_write, "serializable"),
}


async def buyer(strategy, isolation):
    conn = await asyncpg.connect(DSN)
    try:
        async with conn.transaction(isolation=isolation):
            return await strategy(conn)
    except asyncpg.PostgresError as exc:
        return type(exc).__name__
    finally:
        await conn.close()


async def main(args):
    admin = await asyncpg.connect(DSN)
    for name, (strategy, iso) in STRATEGIES.items():
        await admin.execute(
            "update stock_levels set qty = $3"
            f" where {WHERE}", SKU, WAREHOUSE, args.stock)
        start = time.perf_counter()
        results = await asyncio.gather(*(
            buyer(strategy, iso)
            for _ in range(args.buyers)
        ))
        ms = (time.perf_counter() - start) * 1000
        left = await admin.fetchval(
            f"select qty from stock_levels where {WHERE}",
            SKU, WAREHOUSE)
        print(f"{name:<31}{ms:5.0f} ms  left {left}")
        for result, n in sorted(Counter(results).items()):
            print(f"    {n} {result}")
    await admin.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--buyers", type=int, default=8)
    parser.add_argument("--stock", type=int, default=1)
    asyncio.run(main(parser.parse_args()))
