import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from secondloop.db import engine
from secondloop.observability import (
    instrument,
    watch_event_loop,
    watch_pool,
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
    app.include_router(catalog.router)
    app.include_router(checkout.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
