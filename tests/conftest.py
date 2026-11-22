import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@localhost"
    "/secondloop_test",
)

import httpx2
import pytest

from secondloop.main import create_app
from secondloop.partners.parcelpath import (
    Rate,
    parcelpath,
)
from secondloop.seed import seed


@pytest.fixture(scope="session", autouse=True)
async def database():
    await seed()


@pytest.fixture
def fixed_rate(monkeypatch):
    def fake(weight_grams, postcode):
        return Rate("ground", 949, 3)

    monkeypatch.setattr(parcelpath, "get_rate", fake)


@pytest.fixture
async def client():
    app = create_app()
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://test"
    ) as c:
        yield c
