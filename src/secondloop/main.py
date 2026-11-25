import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeout

from secondloop import health
from secondloop.auth import KeyCache, make_idp_http
from secondloop.db import engine
from secondloop.observability import (
    instrument,
    watch_event_loop,
    watch_pool,
    watch_queries,
)
from secondloop.partners.mailer import (
    Mailer,
    make_mailer_http,
)
from secondloop.partners.parcelpath import (
    make_client,
    make_http,
)
from secondloop.routes import (
    account,
    catalog,
    checkout,
    orders,
    search,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    watcher = asyncio.create_task(watch_event_loop())
    async with (
        make_http() as http,
        make_mailer_http() as mail_http,
        make_idp_http() as idp_http,
    ):
        app.state.parcelpath = make_client(http)
        app.state.mailer = Mailer(mail_http)
        app.state.idp_keys = KeyCache(idp_http)
        # Best effort: if the provider is down, start
        # anyway and fetch on the first sign-in.
        await app.state.idp_keys.refresh()
        yield
    watcher.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SecondLoop shop API", lifespan=lifespan
    )
    instrument(app)
    watch_pool(engine)
    watch_queries(engine)
    app.include_router(catalog.router)
    app.include_router(checkout.router)
    app.include_router(search.router)
    app.include_router(orders.router)
    app.include_router(account.router)

    @app.exception_handler(PoolTimeout)
    async def pool_busy(
        request: Request, exc: PoolTimeout
    ):
        return JSONResponse(
            {"detail": "busy, try again"},
            status_code=503,
            headers={"Retry-After": "1"},
        )

    app.include_router(health.router)
    app.state.draining = False
    return app


app = create_app()
