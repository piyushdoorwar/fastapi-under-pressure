"""Request logs, latency metrics and an event-loop
lag monitor for the SecondLoop API."""

import asyncio
import logging
import time
import uuid
from contextvars import ContextVar

import structlog
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.INFO
    ),
)
log = structlog.get_logger()

REQUEST_SECONDS = Histogram(
    "http_request_duration_seconds",
    "Time to handle a request",
    ["method", "route", "status"],
    buckets=(.005, .01, .025, .05, .1, .25,
             .5, 1, 2, 5),
)
LOOP_LAG = Gauge(
    "event_loop_lag_seconds",
    "Lateness of the last event-loop tick",
)

POOL_IN_USE = Gauge(
    "db_pool_connections_in_use",
    "Connections checked out of the pool",
)
POOL_HOLD_SECONDS = Histogram(
    "db_connection_hold_seconds",
    "Time a connection stays checked out",
    buckets=(.005, .01, .025, .05, .1, .25,
             .5, 1, 2, 5),
)
HOLD_WARN = 0.5  # log when a connection is held longer
QUERIES_PER_REQUEST = Histogram(
    "db_queries_per_request",
    "SQL statements sent while handling a request",
    ["route"],
    buckets=(1, 2, 3, 5, 10, 25, 100, 500, 2500),
)
# A one-item list per request, so code running in
# child tasks can add to the same count.
QUERY_COUNT: ContextVar[list[int] | None] = ContextVar(
    "query_count", default=None
)

LAG_INTERVAL = 0.05   # seconds between ticks
LAG_WARN = 0.1        # log when a tick is this late


async def watch_event_loop() -> None:
    """Sleep in a loop and measure how late we wake."""
    while True:
        start = time.perf_counter()
        await asyncio.sleep(LAG_INTERVAL)
        late = time.perf_counter() - start - LAG_INTERVAL
        LOOP_LAG.set(late)
        if late > LAG_WARN:
            log.warning(
                "event_loop_blocked",
                lag_ms=round(late * 1000),
            )


def on_checkout(dbapi_conn, record, proxy):
    record.info["out_at"] = time.perf_counter()
    POOL_IN_USE.inc()


def on_checkin(dbapi_conn, record):
    out_at = record.info.pop("out_at", None)
    if out_at is None:
        return
    held = time.perf_counter() - out_at
    POOL_IN_USE.dec()
    POOL_HOLD_SECONDS.observe(held)
    if held > HOLD_WARN:
        log.warning(
            "db_connection_held",
            held_ms=round(held * 1000),
        )


def watch_pool(engine: AsyncEngine) -> None:
    """Measure how long each connection is checked out."""
    pool = engine.sync_engine.pool
    if not event.contains(pool, "checkout", on_checkout):
        event.listen(pool, "checkout", on_checkout)
        event.listen(pool, "checkin", on_checkin)


def on_execute(conn, cursor, statement, params,
               context, executemany):
    count = QUERY_COUNT.get()
    if count is not None:
        count[0] += 1


def watch_queries(engine: AsyncEngine) -> None:
    """Count SQL statements per request."""
    sync = engine.sync_engine
    if not event.contains(
        sync, "before_cursor_execute", on_execute
    ):
        event.listen(
            sync, "before_cursor_execute", on_execute
        )


def route_of(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


def instrument(app: FastAPI) -> None:
    @app.middleware("http")
    async def observe(request: Request, call_next):
        request_id = (
            request.headers.get("x-request-id")
            or uuid.uuid4().hex[:16]
        )
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
        )
        queries = [0]
        QUERY_COUNT.set(queries)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            seconds = time.perf_counter() - start
            route = route_of(request)
            REQUEST_SECONDS.labels(
                request.method, route, status
            ).observe(seconds)
            QUERIES_PER_REQUEST.labels(route).observe(
                queries[0]
            )
            log.info(
                "request",
                method=request.method,
                route=route,
                status=status,
                ms=round(seconds * 1000, 1),
                queries=queries[0],
            )
            structlog.contextvars.clear_contextvars()

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
