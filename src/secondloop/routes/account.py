"""The account pages: a signed-in customer's orders."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.auth import Customer
from secondloop.db import get_session
from secondloop.models import Order

router = APIRouter()
DB = Annotated[
    AsyncSession, Depends(get_session, scope="function")
]


class AccountOrder(BaseModel):
    number: str
    total_cents: int
    created_at: datetime


@router.get("/account/orders")
async def my_orders(
    email: Customer, db: DB
) -> list[AccountOrder]:
    async with db.begin():
        rows = await db.scalars(
            select(Order)
            .where(Order.email == email)
            .order_by(Order.id.desc())
            .limit(50)
        )
        return [
            AccountOrder(number=o.number,
                         total_cents=o.total_cents,
                         created_at=o.created_at)
            for o in rows
        ]
