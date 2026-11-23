"""Fill a dict the way the search cache did, empty it,
and watch the process's resident memory (Linux).

    python tools/rss_demo.py
"""

import gc

from secondloop.routes.catalog import ProductOut


def rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def page(n: int) -> list[ProductOut]:
    return [
        ProductOut(
            sku=f"LAP-{n:05d}-{i}", name=f"laptop {n}",
            price_cents=64900, in_stock=True,
            ships_from=["dallas", "reno"],
        )
        for i in range(20)
    ]


def fill() -> dict[str, list[ProductOut]]:
    return {f"/search?q=laptop&ref={n}": page(n)
            for n in range(20_000)}


print(f"start             {rss_mb():5.0f} MB")
cache = fill()
print(f"20,000 entries    {rss_mb():5.0f} MB")
cache.clear()
gc.collect()
print(f"after clear()     {rss_mb():5.0f} MB")

cache = fill()
print(f"filled again      {rss_mb():5.0f} MB")
for i, key in enumerate(list(cache)):
    if i % 10:                  # drop 9 entries in 10
        del cache[key]
gc.collect()
print(f"kept 1 in 10      {rss_mb():5.0f} MB")
