"""Create the schema and load the SecondLoop catalogue.

Run with: python -m secondloop.seed
"""

import asyncio

from secondloop.db import Session, engine
from secondloop.models import Base, Product

CATALOGUE = [
    ("LAP-14-R", "14in laptop, refurbished",
     64900, 1800, 25),
    ("CHG-65-C", "65W USB-C charger",
     3900, 300, 140),
    ("HDP-BT-R", "Bluetooth headphones, refurbished",
     8900, 250, 60),
    ("PHN-12-R", "12 phone, refurbished",
     32900, 400, 35),
    ("TAB-10-R", "10in tablet, refurbished",
     27900, 650, 18),
    ("KBD-MX-R", "Mechanical keyboard, refurbished",
     5900, 900, 42),
]


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with Session() as session:
        session.add_all(
            Product(
                sku=sku, name=name, price_cents=price,
                weight_grams=grams, stock=stock,
            )
            for sku, name, price, grams, stock
            in CATALOGUE
        )
        await session.commit()
    await engine.dispose()
    print(f"seeded {len(CATALOGUE)} products")


if __name__ == "__main__":
    asyncio.run(seed())
