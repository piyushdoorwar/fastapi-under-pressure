import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from secondloop.observability import (
    instrument,
    watch_event_loop,
)
from secondloop.routes import catalog, checkout


@asynccontextmanager
async def lifespan(app: FastAPI):
    watcher = asyncio.create_task(watch_event_loop())
    yield
    watcher.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SecondLoop shop API", lifespan=lifespan
    )
    instrument(app)
    app.include_router(catalog.router)
    app.include_router(checkout.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
