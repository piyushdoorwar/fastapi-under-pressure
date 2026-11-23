import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeout

from secondloop.db import engine
from secondloop.observability import (
    instrument,
    watch_event_loop,
    watch_pool,
    watch_queries,
)
from secondloop.partners.parcelpath import (
    ParcelPathClient,
    make_http,
)
from secondloop.routes import catalog, checkout


@asynccontextmanager
async def lifespan(app: FastAPI):
    watcher = asyncio.create_task(watch_event_loop())
    async with make_http() as http:
        app.state.parcelpath = ParcelPathClient(http)
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

    @app.exception_handler(PoolTimeout)
    async def pool_busy(request: Request, exc: PoolTimeout):
        return JSONResponse(
            {"detail": "busy, try again"},
            status_code=503,
            headers={"Retry-After": "1"},
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
