"""Find which lines of code are holding on to memory.

Runs the app in-process, sends the same kind of
search traffic as tools/crawl.py, and compares two
tracemalloc snapshots: one after a warm-up and one at
the end. Lines whose allocations are still alive at
the end, and grew in between, are the suspects.

    python tools/memory_probe.py --searches 3000
"""

import argparse
import asyncio
import logging
import tracemalloc

import httpx2
import structlog
from tools.crawl import searches

from secondloop.main import create_app


async def send(client, n, seed):
    for params in searches(n, seed):
        await client.get("/search", params=params)


async def main(args):
    quiet = structlog.make_filtering_bound_logger(
        logging.WARNING
    )
    structlog.configure(wrapper_class=quiet)
    app = create_app()
    transport = httpx2.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=transport, base_url="http://probe"
        ) as client,
    ):
        await send(client, 200, seed=0)   # warm up
        tracemalloc.start(10)
        before = tracemalloc.take_snapshot()
        await send(client, args.searches, seed=1)
        after = tracemalloc.take_snapshot()
    stats = after.compare_to(before, "traceback")
    total = sum(s.size_diff for s in stats)
    print(f"grew {total / 2**20:.1f} MiB over "
          f"{args.searches} searches")
    # Charge each allocation to the innermost line of
    # our own code that led to it.
    by_line: dict[str, list[int]] = {}
    for stat in stats:
        ours = [f for f in stat.traceback
                if "/secondloop/" in f.filename]
        if not ours:
            continue
        f = ours[-1]
        name = f.filename.split("/secondloop/")[-1]
        size, count = by_line.setdefault(
            f"{name}:{f.lineno}", [0, 0]
        )
        by_line[f"{name}:{f.lineno}"] = [
            size + stat.size_diff,
            count + stat.count_diff,
        ]
    top = sorted(
        by_line.items(), key=lambda kv: -kv[1][0]
    )
    for line, (size, count) in top[:args.top]:
        print(f"{size / 2**20:6.1f} MiB {count:+8d} "
              f"objects  {line}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--searches", type=int, default=3000)
    ap.add_argument("--top", type=int, default=5)
    asyncio.run(main(ap.parse_args()))
