"""Create the schema and load the SecondLoop catalogue.

Run with: python -m secondloop.seed

The six products the book uses by name come first.
The rest is generated, so the catalogue has the size
of the real one after the sale import.
"""

import asyncio
import os
import random

from secondloop.db import Session, engine
from secondloop.models import Base, Product, StockLevel

NAMED = [
    ("LAP-14-R", "14in laptop, refurbished", 64900, 1800),
    ("CHG-65-C", "65W USB-C charger", 3900, 300),
    ("HDP-BT-R", "Bluetooth headphones, refurbished",
     8900, 250),
    ("PHN-12-R", "12 phone, refurbished", 32900, 400),
    ("TAB-10-R", "10in tablet, refurbished", 27900, 650),
    ("KBD-MX-R", "Mechanical keyboard, refurbished",
     5900, 900),
]
KINDS = [
    ("LAP", "laptop", 30000, 90000, 1600),
    ("PHN", "phone", 12000, 60000, 400),
    ("TAB", "tablet", 15000, 50000, 650),
    ("MON", "monitor", 9000, 40000, 4500),
    ("HDP", "headphones", 3000, 25000, 250),
    ("WAT", "smartwatch", 8000, 30000, 150),
    ("KBD", "keyboard", 2500, 12000, 900),
    ("CHG", "charger", 1500, 6000, 300),
]
WAREHOUSES = ["dallas", "oakland", "reno"]
SIZE = int(os.getenv("CATALOGUE_SIZE", "2000"))


def catalogue(size: int):
    rng = random.Random(42)
    yield from NAMED
    for n in range(size - len(NAMED)):
        code, kind, low, high, grams = rng.choice(KINDS)
        price = rng.randrange(low, high, 100) - 1
        yield (f"{code}-{n:04d}",
               f"Refurbished {kind} #{n}", price, grams)


# The phone in Ben's ticket: one left, in Dallas.
FIXED_STOCK = {"PHN-12-R": {"dallas": 1}}


def stock(sku: str, rng: random.Random):
    if sku in FIXED_STOCK:
        for warehouse in WAREHOUSES:
            qty = FIXED_STOCK[sku].get(warehouse, 0)
            yield StockLevel(
                sku=sku, warehouse=warehouse, qty=qty
            )
        return
    for warehouse in WAREHOUSES:
        qty = rng.choice([0, 0, 1, 3, 8, 20])
        yield StockLevel(
            sku=sku, warehouse=warehouse, qty=qty
        )


async def seed(size: int = SIZE) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    rng = random.Random(7)
    async with Session() as session:
        for sku, name, price, grams in catalogue(size):
            session.add(Product(
                sku=sku, name=name, price_cents=price,
                weight_grams=grams,
            ))
            session.add_all(stock(sku, rng))
        await session.commit()
    await engine.dispose()
    print(f"seeded {size} products")


if __name__ == "__main__":
    asyncio.run(seed())
