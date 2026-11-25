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
os.environ["IDP_URL"] = "http://127.0.0.1:8093"
os.environ["IDP_REFRESH_COOLDOWN_S"] = "0.5"
os.environ["MAILER_TIMEOUT_S"] = "0.2"
os.environ["OUTBOX_LEASE_S"] = "0.5"

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


@pytest.fixture
async def partner(slow_partner):
    """Change how the fake ParcelPath behaves for one
    test, and put it back afterwards."""
    async with httpx2.AsyncClient(
        base_url="http://127.0.0.1:8091"
    ) as admin:
        async def set_mode(**mode):
            await admin.put("/_fake/mode", json=mode)

        yield set_mode
        await set_mode(delay_ms=300, status=200,
                       version="1.3", body=None)


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


@pytest.fixture(scope="session", autouse=True)
def idp_server():
    """Run the fake identity provider on port 8093.
    Every app's startup fetches its keys, so it runs
    for every test."""
    from fakes.idp import app

    server = uvicorn.Server(uvicorn.Config(
        app, port=8093, log_level="warning"
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
async def idp():
    """Get tokens from the fake identity provider, and
    make it rotate keys or run a fast clock."""
    async with httpx2.AsyncClient(
        base_url="http://127.0.0.1:8093"
    ) as http:
        class Idp:
            async def token(self, email, ttl_s=300):
                resp = await http.post("/token", json={
                    "email": email, "ttl_s": ttl_s,
                })
                return resp.json()["access_token"]

            async def mode(self, **mode):
                resp = await http.put(
                    "/_fake/mode", json=mode
                )
                return resp.json()

            async def stats(self):
                resp = await http.get("/_fake/stats")
                return resp.json()

        yield Idp()
        await http.put(
            "/_fake/mode", json={"reset": True}
        )


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

            async def slow(self, ms):
                await mail.put(
                    "/_fake/mode", json={"delay_ms": ms}
                )

        yield Inbox()
        await mail.put("/_fake/mode", json={})


@pytest.fixture
async def delivered(inbox):
    """Do the worker's job once: send what the outbox
    holds (chapter 12)."""
    from secondloop.outbox import deliver_pending
    from secondloop.partners.mailer import (
        Mailer,
        make_mailer_http,
    )

    async with make_mailer_http() as http:
        async def run():
            return await deliver_pending(Mailer(http))

        yield run
