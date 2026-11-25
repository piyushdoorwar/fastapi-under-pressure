"""The worker: sends queued confirmation emails.

    python -m secondloop.worker

Run one or more of these next to the API. On SIGTERM it
finishes the email it is sending, then exits. If it is
killed instead, the email it was sending stays in the
outbox and is sent again.
"""

import asyncio
import signal
import time

import structlog
from prometheus_client import Gauge, start_http_server

import secondloop.observability  # noqa: F401  JSON logs
from secondloop.outbox import (
    backlog,
    deliver_pending,
    forget_old_keys,
)
from secondloop.partners.mailer import (
    Mailer,
    make_mailer_http,
)
from secondloop.settings import settings

log = structlog.get_logger()
OLDEST = Gauge(
    "outbox_oldest_unsent_seconds",
    "How long the oldest waiting email has waited",
)
DEAD = Gauge(
    "outbox_dead_letters",
    "Emails given up on, waiting for a person",
)


async def run(stop: asyncio.Event) -> None:
    last_cleanup = 0.0
    async with make_mailer_http() as http:
        mailer = Mailer(http)
        log.info("worker_started")
        while not stop.is_set():
            await deliver_pending(mailer, stop)
            age, dead = await backlog()
            OLDEST.set(age)
            DEAD.set(dead)
            if time.monotonic() - last_cleanup > 3600:
                await forget_old_keys()
                last_cleanup = time.monotonic()
            try:
                await asyncio.wait_for(
                    stop.wait(), settings.worker_poll_s
                )
            except TimeoutError:
                pass
    log.info("worker_stopped")


def main() -> None:
    stop = asyncio.Event()
    if settings.worker_metrics_port:
        start_http_server(settings.worker_metrics_port)

    async def start():
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await run(stop)

    asyncio.run(start())


if __name__ == "__main__":
    main()
