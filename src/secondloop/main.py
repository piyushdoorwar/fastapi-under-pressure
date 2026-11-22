from fastapi import FastAPI

from secondloop.routes import catalog, checkout


def create_app() -> FastAPI:
    app = FastAPI(title="SecondLoop shop API")
    app.include_router(catalog.router)
    app.include_router(checkout.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
