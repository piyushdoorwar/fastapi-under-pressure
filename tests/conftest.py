import os
import threading
import time

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@localhost"
    "/secondloop_test",
)
os.environ["PARCELPATH_URL"] = "http://127.0.0.1:8091"

import httpx2
import pytest
import uvicorn

from secondloop.main import create_app
from secondloop.partners.parcelpath import (
    Rate,
    get_parcelpath,
)
from secondloop.seed import seed


@pytest.fixture(scope="session", autouse=True)
async def database():
    await seed()


class FixedRate:
    async def get_rate(self, weight_grams, postcode):
        return Rate("ground", 949, 3)


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def fixed_rate(app):
    app.dependency_overrides[get_parcelpath] = FixedRate


@pytest.fixture
async def client(app):
    transport = httpx2.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c,
    ):
        yield c


@pytest.fixture(scope="session")
def slow_partner():
    """Run the fake ParcelPath on port 8091, in its own
    thread and event loop, answering in 300 ms."""
    os.environ["PARCELPATH_DELAY_MS"] = "300"
    os.environ["PARCELPATH_JITTER_MS"] = "0"
    from fakes.parcelpath import app

    server = uvicorn.Server(uvicorn.Config(
        app, port=8091, log_level="warning"
    ))
    thread = threading.Thread(
        target=server.run, daemon=True
    )
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield
    server.should_exit = True
    thread.join()
