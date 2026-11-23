"""Chapter 7 guardrails: the search cache ignores
parameters that don't change the answer, has a fixed
size, and search traffic doesn't grow memory."""

import tracemalloc

from secondloop.routes import search


async def test_tracking_params_share_a_cache_entry(client):
    search.CACHE.clear()
    for ref in ("a1", "b2", "c3"):
        resp = await client.get(
            "/search", params={"q": "laptop", "ref": ref}
        )
        assert resp.status_code == 200
    assert len(search.CACHE) == 1


async def test_cache_has_a_fixed_size(client):
    search.CACHE.clear()
    limit = search.CACHE_SIZE
    for n in range(limit + 50):
        await client.get("/search", params={"q": f"#{n}"})
    assert len(search.CACHE) <= limit


async def test_search_traffic_does_not_grow_memory(
    client,
):
    await client.get("/search", params={"q": "laptop"})
    tracemalloc.start()
    before, _ = tracemalloc.get_traced_memory()
    for n in range(300):
        await client.get(
            "/search",
            params={"q": "laptop", "ref": f"visit-{n}"},
        )
    after, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    grew_kb = (after - before) / 1024
    assert grew_kb < 256, f"grew {grew_kb:.0f} KiB"


def test_cache_evicts_oldest_and_expires():
    from secondloop.cache import TTLCache

    now = [0.0]
    cache = TTLCache(
        max_entries=2, ttl_s=60, clock=lambda: now[0]
    )
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")       # "a" is now the most recent
    cache.put("c", 3)    # so "b" goes
    assert cache.get("b") is None
    assert cache.get("a") == 1
    now[0] = 61.0
    assert cache.get("a") is None  # expired
