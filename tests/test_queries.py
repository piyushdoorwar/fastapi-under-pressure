"""Chapter 5 guardrails: the catalogue must cost the
same number of queries however big it gets, and must
never return the whole catalogue in one response."""

from contextlib import contextmanager

from sqlalchemy import event

from secondloop.db import engine


@contextmanager
def count_queries():
    statements: list[str] = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)

    sync = engine.sync_engine
    event.listen(sync, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(
            sync, "before_cursor_execute", record
        )


async def test_catalogue_query_count_is_constant(client):
    with count_queries() as statements:
        resp = await client.get("/products")
    assert resp.status_code == 200
    assert len(statements) <= 2, (
        f"{len(statements)} queries for one page"
    )


async def test_catalogue_is_paginated(client):
    first = await client.get("/products?limit=5")
    assert len(first.json()) == 5
    after = first.headers["x-next-after"]
    assert after == first.json()[-1]["sku"]

    second = await client.get(
        f"/products?limit=5&after={after}"
    )
    skus = [p["sku"] for p in second.json()]
    assert skus[0] > after
    assert len(skus) == 5
