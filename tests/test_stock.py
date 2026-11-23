"""Chapter 9 guardrails: stock is taken once, however
many orders arrive at the same moment."""

import asyncio

from sqlalchemy import func, select, update

from secondloop.db import Session
from secondloop.models import OrderLine, StockLevel


async def set_stock(sku: str, **by_warehouse: int):
    async with Session.begin() as s:
        await s.execute(
            update(StockLevel)
            .where(StockLevel.sku == sku)
            .values(qty=0)
        )
        for warehouse, qty in by_warehouse.items():
            await s.execute(
                update(StockLevel)
                .where(StockLevel.sku == sku,
                       StockLevel.warehouse == warehouse)
                .values(qty=qty)
            )


async def stock_of(sku: str) -> int:
    async with Session() as s:
        return await s.scalar(
            select(func.sum(StockLevel.qty))
            .where(StockLevel.sku == sku)
        )


async def sold(sku: str) -> int:
    async with Session() as s:
        return await s.scalar(
            select(func.sum(OrderLine.qty))
            .where(OrderLine.sku == sku)
        ) or 0


def cart(n, *lines):
    return {
        "lines": [{"sku": s, "qty": q} for s, q in lines],
        "postcode": "94107",
        "email": f"buyer{n}@example.com",
    }


async def at_once(client, carts):
    return [r.status_code for r in await asyncio.gather(
        *(client.post("/orders", json=c) for c in carts)
    )]


async def test_last_one_sells_once(client, inbox):
    await set_stock("TAB-10-R", dallas=1)
    before = await sold("TAB-10-R")
    codes = await at_once(client, [
        cart(n, ("TAB-10-R", 1)) for n in range(8)
    ])
    assert sorted(codes) == [201] + [409] * 7
    assert await sold("TAB-10-R") - before == 1
    assert await stock_of("TAB-10-R") == 0


async def test_stock_across_warehouses(client, inbox):
    await set_stock("HDP-BT-R", dallas=2, reno=1)
    before = await sold("HDP-BT-R")
    codes = await at_once(client, [
        cart(n, ("HDP-BT-R", 1)) for n in range(8)
    ])
    assert codes.count(201) == 3
    assert await sold("HDP-BT-R") - before == 3
    assert await stock_of("HDP-BT-R") == 0


async def test_crossed_carts_do_not_deadlock(
    client, inbox
):
    await set_stock("KBD-MX-R", oakland=50)
    await set_stock("CHG-65-C", oakland=50)
    one = ("KBD-MX-R", 1)
    two = ("CHG-65-C", 1)
    codes = await at_once(client, [
        cart(n, one, two) if n % 2 else cart(n, two, one)
        for n in range(10)
    ])
    assert codes == [201] * 10
    assert await stock_of("KBD-MX-R") == 40
