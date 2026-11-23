"""A small load generator for the SecondLoop API.

Each virtual user loops: pick a request, send it,
record how long it took. The 2-second client timeout
matches the storefront's, so a timeout here is a
"Something went wrong" page for a customer.

    python tools/load.py --users 20 --seconds 30
"""

import argparse
import asyncio
import random
import statistics
import time
from collections import defaultdict

import httpx2

CART = {
    "lines": [
        {"sku": "LAP-14-R", "qty": 1},
        {"sku": "CHG-65-C", "qty": 1},
    ],
    "postcode": "94107",
}
MIX = [
    ("GET /products", 0.7),
    ("POST /checkout/quote", 0.3),
]


async def call(client, name):
    if name == "GET /products":
        return await client.get("/products")
    return await client.post("/checkout/quote", json=CART)


async def user(client, deadline, results):
    names = [n for n, _ in MIX]
    weights = [w for _, w in MIX]
    while time.monotonic() < deadline:
        name = random.choices(names, weights)[0]
        start = time.perf_counter()
        try:
            resp = await call(client, name)
            ok = resp.status_code < 500
        except httpx2.TimeoutException:
            ok = None  # timed out
        except httpx2.HTTPError:
            ok = False
        ms = (time.perf_counter() - start) * 1000
        results[name].append((ms, ok))


def pct(values, p):
    if len(values) == 1:
        return values[0]
    q = statistics.quantiles(
        values, n=100, method="inclusive"
    )
    return q[p - 1]


def report(results, seconds):
    print(f"{'route':<21}{'reqs':>5}{'p50':>6}"
          f"{'p95':>6}{'p99':>6}{'max':>6}{'t/o':>4}"
          f"{'err':>4}")
    for name, rows in sorted(results.items()):
        ms = [m for m, _ in rows]
        timeouts = sum(1 for _, ok in rows if ok is None)
        errors = sum(1 for _, ok in rows if ok is False)
        print(f"{name:<21}{len(rows):>5}"
              f"{pct(ms, 50):>6.0f}{pct(ms, 95):>6.0f}"
              f"{pct(ms, 99):>6.0f}{max(ms):>6.0f}"
              f"{timeouts:>4}{errors:>4}")
    total = sum(len(r) for r in results.values())
    print(f"throughput: {total / seconds:.1f} req/s"
          "  (times in ms; err = 5xx or failed)")


async def main(args):
    results = defaultdict(list)
    limits = httpx2.Limits(max_connections=args.users)
    async with httpx2.AsyncClient(
        base_url=args.url, timeout=2.0, limits=limits,
    ) as client:
        deadline = time.monotonic() + args.seconds
        await asyncio.gather(*(
            user(client, deadline, results)
            for _ in range(args.users)
        ))
    report(results, args.seconds)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=1)
    ap.add_argument("--seconds", type=int, default=20)
    asyncio.run(main(ap.parse_args()))
