"""Measure what different kinds of work do to the
event loop, and how many threads FastAPI lends you.

    python tools/blocking_demo.py
"""

import asyncio
import hashlib
import time

from anyio import to_thread


def hash_password() -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", b"hunter2", b"salt", 600_000
    )


async def ticker(lags: list[float]) -> None:
    while True:
        start = time.perf_counter()
        await asyncio.sleep(0.01)
        lags.append(time.perf_counter() - start - 0.01)


async def measure(label, work) -> None:
    lags: list[float] = []
    tick = asyncio.create_task(ticker(lags))
    await asyncio.sleep(0.05)
    start = time.perf_counter()
    await work()
    took = time.perf_counter() - start
    await asyncio.sleep(0.02)  # let the ticker wake
    tick.cancel()
    print(f"{label:<28} took {took * 1000:5.0f} ms"
          f"   worst lag {max(lags) * 1000:4.0f} ms")


async def inline_hash():
    hash_password()


async def threaded_hash():
    await to_thread.run_sync(hash_password)


async def hundred_sleeps():
    # 100 blocking 0.5 s calls sent to the threadpool
    await asyncio.gather(*(
        to_thread.run_sync(time.sleep, 0.5)
        for _ in range(100)
    ))


async def main():
    limiter = to_thread.current_default_thread_limiter()
    print(f"threadpool size: {limiter.total_tokens}")
    await measure("hash in async def", inline_hash)
    await measure("hash in a worker thread",
                  threaded_hash)
    await measure("100 x sleep(0.5) in threads",
                  hundred_sleeps)


asyncio.run(main())
