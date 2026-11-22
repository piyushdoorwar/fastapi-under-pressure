"""Request logs, latency metrics and an event-loop
lag monitor for the SecondLoop API."""

import asyncio
import logging
import time
import uuid

import structlog
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Gauge,
    Histogram,
    generate_latest,
)

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
            request_id=request_id
        )
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
            log.info(
                "request",
                method=request.method,
                route=route,
                status=status,
                ms=round(seconds * 1000, 1),
            )
            structlog.contextvars.clear_contextvars()

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
