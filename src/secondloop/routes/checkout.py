from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.db import get_session
from secondloop.models import Product
from secondloop.partners.parcelpath import (
    ParcelPathClient,
    PartnerUnavailable,
    Rate,
    get_parcelpath,
)

router = APIRouter()
DB = Annotated[
    AsyncSession, Depends(get_session, scope="function")
]
ParcelPath = Annotated[
    ParcelPathClient, Depends(get_parcelpath)
]


class Line(BaseModel):
    sku: str
    qty: int = Field(ge=1, le=10)


class QuoteIn(BaseModel):
    lines: list[Line] = Field(min_length=1)
    postcode: str


class QuoteOut(BaseModel):
    quote_id: str
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    eta_days: int
    shipping_estimated: bool


def estimate(weight_grams: int) -> Rate:
    """SecondLoop's own shipping table, used when
    ParcelPath can't answer in time. It's set a little
    above ParcelPath's prices, and SecondLoop pays any
    difference."""
    kilos = max(1, -(-weight_grams // 1000))
    return Rate("ground", 599 + 200 * kilos, 5)


@router.post("/checkout/quote")
async def quote(
    body: QuoteIn, db: DB, parcelpath: ParcelPath
) -> QuoteOut:
    skus = [line.sku for line in body.lines]
    async with db.begin():
        rows = await db.scalars(
            select(Product).where(Product.sku.in_(skus))
        )
        products = {p.sku: p for p in rows}
    # The transaction is over and the connection is
    # back in the pool before we call ParcelPath.
    missing = set(skus) - products.keys()
    if missing:
        raise HTTPException(
            422, f"unknown sku: {sorted(missing)}"
        )

    subtotal = weight = 0
    for line in body.lines:
        p = products[line.sku]
        subtotal += p.price_cents * line.qty
        weight += p.weight_grams * line.qty

    estimated = False
    try:
        rate = await parcelpath.get_rate(
            weight, body.postcode
        )
    except PartnerUnavailable:
        rate = estimate(weight)
        estimated = True
    return QuoteOut(
        quote_id=uuid4().hex[:12],
        subtotal_cents=subtotal,
        shipping_cents=rate.amount_cents,
        total_cents=subtotal + rate.amount_cents,
        eta_days=rate.eta_days,
        shipping_estimated=estimated,
    )
