"""Chapter 14 guardrails: health checks that tell the
balancer the truth, and a process that drains before
it stops."""

import os
import signal
import subprocess
import sys
import time

import httpx2

PORT = 8096


async def status(client, path):
    return (await client.get(path)).status_code


async def test_ready_when_it_can_serve(client):
    assert await status(client, "/readyz") == 200


async def test_not_ready_without_database(
    client, monkeypatch
):
    from secondloop import health

    async def no_database():
        return False

    monkeypatch.setattr(
        health, "database_ok", no_database
    )
    assert await status(client, "/readyz") == 503
    # Still alive: restarting it wouldn't help.
    assert await status(client, "/healthz") == 200


async def test_not_ready_while_draining(app, client):
    app.state.draining = True
    assert await status(client, "/readyz") == 503
    assert await status(client, "/healthz") == 200


def get(path):
    try:
        url = f"http://127.0.0.1:{PORT}{path}"
        return httpx2.get(url, timeout=0.5).status_code
    except httpx2.HTTPError:
        return None


def test_sigterm_drains_then_stops():
    env = {**os.environ, "DRAIN_S": "1.0"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "secondloop.serve",
         "--port", str(PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if get("/readyz") == 200:
                break
            time.sleep(0.05)
        assert get("/readyz") == 200
        proc.send_signal(signal.SIGTERM)
        time.sleep(0.3)
        # Out of rotation, but still answering.
        assert get("/readyz") == 503
        assert get("/products?limit=1") == 200
        assert proc.wait(timeout=5) == 0
    finally:
        proc.kill()
