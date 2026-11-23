from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.db import get_session
from secondloop.models import Product

router = APIRouter()
DB = Annotated[
    AsyncSession, Depends(get_session, scope="function")
]


class ProductOut(BaseModel):
    sku: str
    name: str
    price_cents: int
    in_stock: bool
    ships_from: list[str]


async def to_out(p: Product) -> ProductOut:
    levels = await p.awaitable_attrs.stock_levels
    ships_from = [s.warehouse for s in levels if s.qty]
    return ProductOut(
        sku=p.sku, name=p.name,
        price_cents=p.price_cents,
        in_stock=bool(ships_from),
        ships_from=ships_from,
    )


@router.get("/products")
async def list_products(db: DB) -> list[ProductOut]:
    rows = await db.scalars(
        select(Product).order_by(Product.sku)
    )
    return [await to_out(p) for p in rows]


@router.get("/products/{sku}")
async def get_product(sku: str, db: DB) -> ProductOut:
    product = await db.get(Product, sku)
    if product is None:
        raise HTTPException(404, "unknown sku")
    return await to_out(product)
