"""Run the API with a drain period before shutdown.

    python -m secondloop.serve --port 8000

On SIGTERM the process first stops saying it is ready
(/readyz answers 503) but keeps serving for
`drain_s` seconds, so the balancer has time to notice
and stop sending it new requests. Then Uvicorn shuts
down as usual: it stops accepting connections and
finishes the requests in flight, for at most
`shutdown_timeout_s`. A second SIGTERM or Ctrl+C skips
the drain.
"""

import argparse
import time

import uvicorn

from secondloop.main import app
from secondloop.settings import settings


class DrainingServer(uvicorn.Server):
    drain_until: float | None = None

    def handle_exit(self, sig, frame) -> None:
        if self.drain_until is None and settings.drain_s:
            app.state.draining = True
            self.drain_until = time.monotonic() + (
                settings.drain_s
            )
            return
        super().handle_exit(sig, frame)

    async def on_tick(self, counter: int) -> bool:
        if (self.drain_until is not None
                and time.monotonic() >= self.drain_until):
            self.should_exit = True
        return await super().on_tick(counter)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    config = uvicorn.Config(
        app, host=args.host, port=args.port,
        access_log=False,
        timeout_graceful_shutdown=int(
            settings.shutdown_timeout_s
        ),
    )
    DrainingServer(config).run()


if __name__ == "__main__":
    main()
