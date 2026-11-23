"""Place an order.

The order of the steps is the point of this module:

1. Read the products and ask ParcelPath for a rate,
   with no transaction open (chapter 4).
2. In one short transaction, check and take the
   stock and save the order. If anything fails, the
   whole transaction rolls back and nothing has
   happened.
3. Only after the commit, tell the customer.

A request with an Idempotency-Key that has already
made an order gets that order back (chapter 10).
"""

from typing import Annotated

import structlog
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.db import get_session
from secondloop.idempotency import (
    claim,
    find,
    fingerprint,
    link,
)
from secondloop.models import (
    ORDER_NUMBERS,
    Order,
    OrderLine,
    Product,
    StockLevel,
)
from secondloop.partners.mailer import (
    Mailer,
    MailerError,
    get_mailer,
)
from secondloop.partners.parcelpath import (
    ParcelPathClient,
    PartnerUnavailable,
    get_parcelpath,
)
from secondloop.routes.checkout import Line, estimate

log = structlog.get_logger()
router = APIRouter()
DB = Annotated[
    AsyncSession, Depends(get_session, scope="function")
]
ParcelPath = Annotated[
    ParcelPathClient, Depends(get_parcelpath)
]
Mail = Annotated[Mailer, Depends(get_mailer)]
Key = Annotated[
    str | None,
    Header(alias="Idempotency-Key", min_length=8,
           max_length=100),
]


class OrderIn(BaseModel):
    lines: list[Line] = Field(min_length=1)
    postcode: str
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$")


class OrderOut(BaseModel):
    number: str
    total_cents: int
    shipping_estimated: bool
    confirmation_sent: bool


def out_of_stock(sku: str) -> HTTPException:
    return HTTPException(409, f"not enough stock: {sku}")


class AlreadyPlaced(Exception):
    """Another request with this key made the order."""


def replay(response: Response, order: Order) -> OrderOut:
    log.info("order_replayed", order=order.number)
    response.headers["Idempotent-Replayed"] = "true"
    return OrderOut(
        number=order.number,
        total_cents=order.total_cents,
        shipping_estimated=order.shipping_estimated,
        confirmation_sent=(
            order.confirmation_sent_at is not None
        ),
    )


@router.post("/orders", status_code=201)
async def place_order(
    body: OrderIn,
    db: DB,
    parcelpath: ParcelPath,
    mailer: Mail,
    response: Response,
    key: Key = None,
) -> OrderOut:
    skus = [line.sku for line in body.lines]
    digest = fingerprint(body)
    if key:
        async with db.begin():
            done = await find(db, key, digest)
        if done:
            return replay(response, done)

    # 1. Read, then talk to ParcelPath outside any
    #    transaction.
    async with db.begin():
        rows = await db.scalars(
            select(Product).where(Product.sku.in_(skus))
        )
        products = {p.sku: p for p in rows}
    if missing := set(skus) - products.keys():
        raise HTTPException(
            422, f"unknown sku: {sorted(missing)}"
        )
    weight = sum(products[ln.sku].weight_grams * ln.qty
                 for ln in body.lines)
    estimated = False
    try:
        rate = await parcelpath.get_rate(
            weight, body.postcode
        )
    except PartnerUnavailable:
        rate, estimated = estimate(weight), True

    # 2. One transaction: take the stock, save the order.
    try:
        async with db.begin():
            if key and not await claim(db, key, digest):
                raise AlreadyPlaced
            order = await save_order(
                db, body, products, rate, estimated
            )
            if key:
                await link(db, key, order)
    except AlreadyPlaced:
        async with db.begin():
            done = await find(db, key, digest)
        return replay(response, done)
    except IntegrityError as exc:
        if "stock_not_negative" in str(exc.orig):
            raise out_of_stock(skus[0]) from exc
        raise

    # 3. The order is committed. Now tell the customer.
    sent = await confirm(db, mailer, order)
    return OrderOut(
        number=order.number,
        total_cents=order.total_cents,
        shipping_estimated=estimated,
        confirmation_sent=sent,
    )


async def save_order(
    db, body, products, rate, estimated
) -> Order:
    seq = await db.scalar(ORDER_NUMBERS.next_value())
    order = Order(number=f"SL-{seq}", email=body.email,
                  postcode=body.postcode,
                  shipping_estimated=estimated)
    subtotal = 0
    # Lock stock rows in one order (by SKU) in every
    # transaction, so two carts can't wait on each other.
    for line in sorted(body.lines, key=lambda ln: ln.sku):
        product = products[line.sku]
        warehouse = await take_stock(
            db, line.sku, line.qty
        )
        order.lines.append(OrderLine(
            sku=line.sku, warehouse=warehouse,
            qty=line.qty, price_cents=product.price_cents,
        ))
        subtotal += product.price_cents * line.qty
    order.subtotal_cents = subtotal
    order.shipping_cents = rate.amount_cents
    order.total_cents = subtotal + rate.amount_cents
    db.add(order)
    return order


async def take_stock(db, sku: str, qty: int) -> str:
    """Take qty units of sku from the warehouse with the
    most, checking and writing in one statement. Return
    the warehouse, or raise a 409."""
    candidates = await db.scalars(
        select(StockLevel.warehouse)
        .where(StockLevel.sku == sku,
               StockLevel.qty >= qty)
        .order_by(StockLevel.qty.desc())
    )
    for warehouse in candidates.all():
        taken = await db.scalar(
            update(StockLevel)
            .where(StockLevel.sku == sku,
                   StockLevel.warehouse == warehouse,
                   StockLevel.qty >= qty)
            .values(qty=StockLevel.qty - qty)
            .returning(StockLevel.warehouse)
        )
        if taken is not None:
            return taken
    raise out_of_stock(sku)


async def confirm(db, mailer, order: Order) -> bool:
    number = order.number
    try:
        await mailer.send(
            order.email,
            f"Your SecondLoop order {number}",
            f"Thanks! We've received order {number}.",
        )
    except MailerError:
        log.warning("order_confirmation_failed",
                    order=number)
        return False
    async with db.begin():
        await db.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(confirmation_sent_at=func.now())
        )
    return True
