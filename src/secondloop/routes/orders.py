from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.db import get_tx
from secondloop.models import (
    ORDER_NUMBERS,
    Order,
    OrderLine,
    Product,
)
from secondloop.partners.mailer import Mailer, get_mailer
from secondloop.partners.parcelpath import (
    ParcelPathClient,
    PartnerUnavailable,
    get_parcelpath,
)
from secondloop.routes.catalog import WITH_STOCK
from secondloop.routes.checkout import Line, estimate

router = APIRouter()
TX = Annotated[AsyncSession, Depends(get_tx)]
ParcelPath = Annotated[
    ParcelPathClient, Depends(get_parcelpath)
]
Mail = Annotated[Mailer, Depends(get_mailer)]


class OrderIn(BaseModel):
    lines: list[Line] = Field(min_length=1)
    postcode: str
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$")


class OrderOut(BaseModel):
    number: str
    total_cents: int
    shipping_estimated: bool


@router.post("/orders", status_code=201)
async def place_order(
    body: OrderIn,
    db: TX,
    parcelpath: ParcelPath,
    mailer: Mail,
) -> OrderOut:
    skus = [line.sku for line in body.lines]
    rows = await db.scalars(
        select(Product)
        .options(WITH_STOCK)
        .where(Product.sku.in_(skus))
    )
    products = {p.sku: p for p in rows}
    if missing := set(skus) - products.keys():
        raise HTTPException(
            422, f"unknown sku: {sorted(missing)}"
        )

    seq = await db.scalar(ORDER_NUMBERS.next_value())
    number = f"SL-{seq}"
    order = Order(number=number, email=body.email,
                  postcode=body.postcode)
    subtotal = weight = 0
    for line in body.lines:
        p = products[line.sku]
        # Ship from the warehouse with the most stock.
        level = max(p.stock_levels, key=lambda s: s.qty)
        level.qty -= line.qty
        order.lines.append(OrderLine(
            sku=p.sku, warehouse=level.warehouse,
            qty=line.qty, price_cents=p.price_cents,
        ))
        subtotal += p.price_cents * line.qty
        weight += p.weight_grams * line.qty

    estimated = False
    try:
        rate = await parcelpath.get_rate(
            weight, body.postcode
        )
    except PartnerUnavailable:
        rate, estimated = estimate(weight), True
    order.subtotal_cents = subtotal
    order.shipping_cents = rate.amount_cents
    order.total_cents = subtotal + rate.amount_cents
    db.add(order)

    await mailer.send(
        body.email,
        f"Your SecondLoop order {number}",
        f"Thanks! We've received order {number}.",
    )
    return OrderOut(
        number=number,
        total_cents=order.total_cents,
        shipping_estimated=estimated,
    )
