"""Product search for the storefront's search box.

Results are cached in memory, because the same few
searches ("laptop", "iphone", "charger") make up most
of the traffic and the cache makes them instant.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from prometheus_client import Counter
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.db import get_session
from secondloop.models import Product
from secondloop.routes.catalog import (
    WITH_STOCK,
    ProductOut,
    to_out,
)

router = APIRouter()
DB = Annotated[
    AsyncSession, Depends(get_session, scope="function")
]

CACHE: dict[str, list[ProductOut]] = {}
LOOKUPS = Counter(
    "search_cache_lookups_total",
    "Search cache lookups",
    ["result"],
)


@router.get("/search")
async def search(
    request: Request,
    db: DB,
    q: Annotated[str, Query(min_length=2, max_length=60)],
) -> list[ProductOut]:
    key = str(request.url)  # the query and any options
    if key in CACHE:
        LOOKUPS.labels("hit").inc()
        return CACHE[key]
    LOOKUPS.labels("miss").inc()
    pattern = f"%{q.strip().lower()}%"
    rows = await db.scalars(
        select(Product)
        .options(WITH_STOCK)
        .where(or_(
            Product.name.ilike(pattern),
            Product.sku.ilike(pattern),
        ))
        .order_by(Product.sku)
        .limit(20)
    )
    results = [to_out(p) for p in rows]
    CACHE[key] = results
    return results
