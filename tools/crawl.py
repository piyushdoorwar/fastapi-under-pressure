"""Send searches the way the storefront does.

Since the clearance launch, the storefront adds a
`ref` parameter to every search request: an ID that
its analytics uses to tie a search to a visit. Most
customers search for the same few words.

    python tools/crawl.py --searches 20000
"""

import argparse
import asyncio
import random
import time

import httpx2

POPULAR = ["laptop", "phone", "tablet", "monitor",
           "headphones", "watch", "keyboard",
           "charger", "refurbished", "#1"]


def searches(n: int, seed: int):
    rng = random.Random(seed)
    for _ in range(n):
        yield {
            "q": rng.choice(POPULAR),
            "ref": f"{rng.getrandbits(64):016x}",
        }


async def main(args):
    todo = list(searches(args.searches, args.seed))
    start = time.perf_counter()

    async def worker(client):
        while todo:
            params = todo.pop()
            await client.get("/search", params=params)

    async with httpx2.AsyncClient(
        base_url=args.url, timeout=10
    ) as client:
        await asyncio.gather(*(
            worker(client) for _ in range(args.workers)
        ))
    seconds = time.perf_counter() - start
    print(f"{args.searches} searches in {seconds:.1f} s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--searches", type=int, default=20000)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    asyncio.run(main(ap.parse_args()))
