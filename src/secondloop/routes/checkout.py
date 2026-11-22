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
    get_parcelpath,
)

router = APIRouter()
DB = Annotated[AsyncSession, Depends(get_session)]
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


@router.post("/checkout/quote")
async def quote(
    body: QuoteIn, db: DB, parcelpath: ParcelPath
) -> QuoteOut:
    skus = [line.sku for line in body.lines]
    rows = await db.scalars(
        select(Product).where(Product.sku.in_(skus))
    )
    products = {p.sku: p for p in rows}
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

    rate = await parcelpath.get_rate(
        weight, body.postcode
    )
    return QuoteOut(
        quote_id=uuid4().hex[:12],
        subtotal_cents=subtotal,
        shipping_cents=rate.amount_cents,
        total_cents=subtotal + rate.amount_cents,
        eta_days=rate.eta_days,
    )
