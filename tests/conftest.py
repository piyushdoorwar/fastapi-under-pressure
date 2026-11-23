import os
import threading
import time

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@localhost"
    "/secondloop_test",
)
os.environ["PARCELPATH_URL"] = "http://127.0.0.1:8091"
os.environ["MAILER_URL"] = "http://127.0.0.1:8092"

import httpx2
import pytest
import uvicorn

from secondloop.main import create_app
from secondloop.partners.parcelpath import (
    Rate,
    get_parcelpath,
)
from secondloop.seed import seed

TEST_CATALOGUE = 20  # production has 2,000


@pytest.fixture(scope="session", autouse=True)
async def database():
    await seed(TEST_CATALOGUE)


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
    # Like a real server: errors become responses, and
    # errors after the response has gone are not seen.
    transport = httpx2.ASGITransport(
        app=app, raise_app_exceptions=False
    )
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


@pytest.fixture(scope="session")
def mail_server():
    """Run the fake email provider on port 8092."""
    from fakes.mailer import app

    server = uvicorn.Server(uvicorn.Config(
        app, port=8092, log_level="warning"
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


@pytest.fixture
async def inbox(mail_server, slow_partner):
    """Read what the shop API emailed, and make the
    email provider fail on demand."""
    async with httpx2.AsyncClient(
        base_url="http://127.0.0.1:8092"
    ) as mail:
        await mail.delete("/v1/messages")

        class Inbox:
            async def to(self, address):
                resp = await mail.get(
                    "/v1/messages", params={"to": address}
                )
                return resp.json()

            async def fail_with(self, status):
                await mail.put(
                    "/_fake/mode", json={"status": status}
                )

        yield Inbox()
        await mail.put(
            "/_fake/mode", json={"status": 202}
        )
