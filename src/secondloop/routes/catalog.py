from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


WITH_STOCK = selectinload(Product.stock_levels)


def to_out(p: Product) -> ProductOut:
    ships_from = [
        s.warehouse for s in p.stock_levels if s.qty
    ]
    return ProductOut(
        sku=p.sku, name=p.name,
        price_cents=p.price_cents,
        in_stock=bool(ships_from),
        ships_from=ships_from,
    )


@router.get("/products")
async def list_products(
    db: DB,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: str | None = None,
) -> list[ProductOut]:
    query = (
        select(Product)
        .options(WITH_STOCK)
        .order_by(Product.sku)
        .limit(limit)
    )
    if after is not None:
        query = query.where(Product.sku > after)
    page = [to_out(p) for p in await db.scalars(query)]
    if len(page) == limit:
        response.headers["x-next-after"] = page[-1].sku
    return page


@router.get("/products/{sku}")
async def get_product(sku: str, db: DB) -> ProductOut:
    product = await db.get(
        Product, sku, options=[WITH_STOCK]
    )
    if product is None:
        raise HTTPException(404, "unknown sku")
    return to_out(product)
