"""Product search for the storefront's search box.

Results are cached in memory, because the same few
searches ("laptop", "phone", "charger") make up most
of the traffic. The cache is keyed on what changes
the answer, holds a fixed number of entries, and
forgets them after a minute so stock stays fresh.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from prometheus_client import Counter, Gauge
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from secondloop.cache import TTLCache
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

CACHE_SIZE = 500
CACHE: TTLCache[list[ProductOut]] = TTLCache(
    max_entries=CACHE_SIZE, ttl_s=60
)
CACHED = Gauge(
    "search_cache_entries", "Entries in the search cache"
)
LOOKUPS = Counter(
    "search_cache_lookups_total",
    "Search cache lookups",
    ["result"],
)


@router.get("/search")
async def search(
    db: DB,
    q: Annotated[str, Query(min_length=2, max_length=60)],
) -> list[ProductOut]:
    key = " ".join(q.lower().split())  # only the words
    cached = CACHE.get(key)
    if cached is not None:
        LOOKUPS.labels("hit").inc()
        return cached
    LOOKUPS.labels("miss").inc()
    pattern = f"%{key}%"
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
    CACHE.put(key, results)
    CACHED.set(len(CACHE))
    return results
