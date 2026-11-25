"""Replay the book's incidents against a running stack.

    python tools/drills.py            # every drill
    python tools/drills.py --only 9   # one chapter

Each drill sets up the conditions of one incident with
the fakes, sends the traffic that went wrong, and checks
that the outcome is the fixed one. It expects the stack
from `make drills-stack`: the balancer on 8000 with one
API process behind it, the fakes on 8081-8083, a worker,
and the database.

A failed drill means a change has brought an incident
back. Exit status 1 if any drill fails.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
import uuid

import asyncpg
import httpx2

API = os.getenv("DRILL_API", "http://127.0.0.1:8000")
PARTNER = "http://127.0.0.1:8081"
MAILER = "http://127.0.0.1:8082"
IDP = "http://127.0.0.1:8083"
DSN = os.getenv(
    "PG_DSN", "postgresql://postgres@localhost/secondloop"
)
CART = {"lines": [{"sku": "LAP-14-R", "qty": 1},
                  {"sku": "CHG-65-C", "qty": 1}],
        "postcode": "94107"}
DRILLS = []


class Failed(Exception):
    pass


def drill(chapter: int, name: str):
    def register(fn):
        DRILLS.append((chapter, name, fn))
        return fn
    return register


def check(ok: bool, why: str) -> None:
    if not ok:
        raise Failed(why)


async def mode(http, url, **settings) -> None:
    await http.put(f"{url}/_fake/mode", json=settings)


async def breaker_open(http) -> bool:
    text = (await http.get("/metrics")).text
    return "parcelpath_breaker_open 1.0" in text


async def reset(http) -> None:
    await mode(http, PARTNER, delay_ms=180, jitter_ms=40,
               status=200, version="1.3", body=None)
    # A drill that broke ParcelPath leaves the circuit
    # breaker open for a while (chapter 6). Wait for a
    # trial call to close it.
    for _ in range(30):
        if not await breaker_open(http):
            break
        await http.post("/checkout/quote", json=CART)
        await asyncio.sleep(0.5)
    await mode(http, MAILER, status=202, delay_ms=0)
    await mode(http, IDP, skew_s=0)
    await set_stock("KBD-MX-R", "reno", 1000)


def order(email, sku="KBD-MX-R", qty=1):
    return {"lines": [{"sku": sku, "qty": qty}],
            "postcode": "94107", "email": email}


def fresh(name: str) -> str:
    return f"{name}-{uuid.uuid4().hex[:8]}@example.com"


async def timed(coro):
    start = time.perf_counter()
    resp = await coro
    return resp, time.perf_counter() - start


async def db_value(sql, *args):
    conn = await asyncpg.connect(DSN)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


async def set_stock(sku, warehouse, qty) -> None:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(
            "update stock_levels set qty = 0"
            " where sku = $1", sku)
        await conn.execute(
            "update stock_levels set qty = $3"
            " where sku = $1 and warehouse = $2",
            sku, warehouse, qty)
    finally:
        await conn.close()


async def emails_to(http, email) -> int:
    resp = await http.get(f"{MAILER}/v1/messages",
                          params={"to": email})
    return len(resp.json())


@drill(5, "catalogue pages stay fast")
async def catalogue(http):
    times = []
    for _ in range(20):
        resp, took = await timed(
            http.get("/products", params={"limit": 200})
        )
        check(resp.status_code == 200, "not 200")
        times.append(took)
    worst = max(times)
    check(worst < 0.5, f"slowest page {worst:.2f} s")
    return f"slowest of 20 pages {worst * 1000:.0f} ms"


@drill(6, "slow partner: quotes keep their budget")
async def slow_partner(http):
    """Also chapters 3 and 4: a slow partner must not
    slow down pages that don't use it."""
    await mode(http, PARTNER, delay_ms=3000)
    quotes = asyncio.gather(*(
        timed(http.post("/checkout/quote", json=CART))
        for _ in range(10)
    ))
    pages = asyncio.gather(*(
        timed(http.get("/products"))
        for _ in range(10)
    ))
    quotes, pages = await asyncio.gather(quotes, pages)
    worst = max(took for _, took in quotes)
    page = max(took for _, took in pages)
    check(all(r.status_code == 200 for r, _ in quotes),
          "a quote failed")
    check(worst < 1.5, f"slowest quote {worst:.2f} s")
    check(page < 0.3, f"slowest page {page:.2f} s")
    check(all(r.json()["shipping_estimated"]
              for r, _ in quotes), "no estimate")
    return (f"slowest quote {worst:.2f} s (estimated),"
            f" slowest page {page * 1000:.0f} ms")


@drill(6, "partner down: quotes use the estimate")
async def partner_down(http):
    await mode(http, PARTNER, status=503)
    replies = await asyncio.gather(*(
        http.post("/checkout/quote", json=CART)
        for _ in range(10)
    ))
    check(all(r.status_code == 200 for r in replies),
          "a quote failed")
    check(all(r.json()["shipping_estimated"]
              for r in replies), "no estimate")
    return "10 estimated quotes"


@drill(7, "search cache stays bounded")
async def search_cache(http):
    for n in range(600):
        await http.get("/search", params={
            "q": "laptop", "ref": f"drill-{n}"})
    text = (await http.get("/metrics")).text
    line = next(ln for ln in text.splitlines()
                if ln.startswith("search_cache_entries"))
    entries = float(line.split()[-1])
    check(entries <= 500, f"cache size {entries:.0f}")
    return f"cache size {entries:.0f} after 600 searches"


@drill(8, "email down: the order is kept")
async def email_down(http):
    await mode(http, MAILER, status=503)
    email = fresh("drill8")
    resp = await http.post("/orders", json=order(email))
    check(resp.status_code == 201, f"{resp.status_code}")
    saved = await db_value(
        "select count(*) from orders o join outbox m"
        " on m.order_id = o.id where o.email = $1", email)
    check(saved == 1, f"{saved} orders with an email")
    return "order saved, email queued"


@drill(9, "last unit sells once")
async def last_unit(http):
    await set_stock("TAB-10-R", "dallas", 1)
    replies = await asyncio.gather(*(
        http.post("/orders",
                  json=order(fresh("drill9"), "TAB-10-R"))
        for _ in range(8)
    ))
    codes = sorted(r.status_code for r in replies)
    left = await db_value(
        "select sum(qty) from stock_levels"
        " where sku = 'TAB-10-R'")
    check(codes == [201] + [409] * 7, f"{codes}")
    check(left == 0, f"{left} left")
    return "1 sold, 7 refused, 0 left"


@drill(10, "a retried order is one order")
async def retried(http):
    await mode(http, PARTNER, delay_ms=800)
    email = fresh("drill10")
    key = {"Idempotency-Key": str(uuid.uuid4())}
    first = asyncio.create_task(http.post(
        "/orders", json=order(email), headers=key))
    await asyncio.sleep(0.1)
    again = await http.post(
        "/orders", json=order(email), headers=key)
    first = await first
    count = await db_value(
        "select count(*) from orders where email = $1",
        email)
    numbers = {r.json()["number"] for r in (first, again)}
    check(len(numbers) == 1, "different order numbers")
    check(count == 1, f"{count} orders")
    return "same number, 1 order"


@drill(11, "partner format change is read exactly")
async def partner_format(http):
    await mode(http, PARTNER, version="1.4")
    body = (await http.post(
        "/checkout/quote", json=CART)).json()
    check(body["shipping_cents"] == 949,
          f"shipping {body['shipping_cents']}")
    await mode(http, PARTNER,
               body={"service": "ground", "eta_days": 3})
    body = (await http.post(
        "/checkout/quote", json=CART)).json()
    check(body["shipping_estimated"], "no estimate")
    return "v1.4 949, unreadable answer estimated"


async def wait_for_emails(http, email, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if await emails_to(http, email):
            return True
        await asyncio.sleep(0.5)
    return False


@drill(13, "slow email provider sends once")
async def slow_email(http):
    await mode(http, MAILER, delay_ms=2500)
    email = fresh("drill13")
    await http.post("/orders", json=order(email))
    await asyncio.sleep(6)
    await mode(http, MAILER, delay_ms=0)
    check(await wait_for_emails(http, email, 20),
          "no email after 20 s")
    await asyncio.sleep(3)  # late duplicates land
    copies = await emails_to(http, email)
    check(copies == 1, f"{copies} copies")
    return "1 copy"


@drill(13, "bad address doesn't block the queue")
async def bad_address(http):
    bad = f"drill13-{uuid.uuid4().hex[:8]}@example"
    good = fresh("drill13")
    await http.post("/orders", json=order(bad))
    await http.post("/orders", json=order(good))
    check(await wait_for_emails(http, good, 10),
          "good email not sent")
    dead = await db_value(
        "select count(*) from outbox m join orders o"
        " on m.order_id = o.id where o.email = $1"
        " and m.dead_at is not null", bad)
    check(dead == 1, "bad address not set aside")
    conn = await asyncpg.connect(DSN)  # tidy up after
    try:
        await conn.execute(
            "delete from outbox where order_id in"
            " (select id from orders where email = $1)",
            bad)
    finally:
        await conn.close()
    return "dead letter set aside, next email sent"


async def account(http, email):
    token = (await http.post(f"{IDP}/token", json={
        "email": email})).json()["access_token"]
    return await http.get(
        "/account/orders",
        headers={"Authorization": f"Bearer {token}"})


@drill(15, "clock a few seconds apart")
async def clock_skew(http):
    await mode(http, IDP, skew_s=5)
    resp = await account(http, fresh("drill15"))
    check(resp.status_code == 200, f"{resp.status_code}")
    return "accepted"


@drill(15, "signing key rotation")
async def key_rotation(http):
    await mode(http, IDP, rotate=True)
    start = time.monotonic()
    while time.monotonic() - start < 35:
        resp = await account(http, fresh("drill15"))
        if resp.status_code == 200:
            took = time.monotonic() - start
            return f"new key accepted after {took:.0f} s"
        await asyncio.sleep(1)
    raise Failed("still refused after 35 s")


async def load_failures(http, seconds) -> tuple[int, int]:
    ok = failed = 0
    deadline = time.monotonic() + seconds

    async def user():
        nonlocal ok, failed
        while time.monotonic() < deadline:
            try:
                resp = await http.get(
                    "/products", params={"limit": 20})
                if resp.status_code < 500:
                    ok += 1
                else:
                    failed += 1
            except httpx2.HTTPError:
                failed += 1

    await asyncio.gather(*(user() for _ in range(10)))
    return ok, failed


@drill(14, "deploy under load drops nothing")
async def deploy(http):
    try:
        await http.get("/_lb/backends")
    except httpx2.HTTPError as exc:
        raise Failed("no balancer on 8000") from exc
    loading = asyncio.create_task(load_failures(http, 9))
    await asyncio.sleep(1)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "tools/deploy.py",
        stdout=subprocess.DEVNULL,
    )
    await proc.wait()
    ok, failed = await loading
    check(proc.returncode == 0, "deploy failed")
    total = ok + failed
    check(failed == 0, f"{failed} of {total} failed")
    return f"0 of {ok} requests failed"


async def main(args) -> int:
    by_chapter = sorted(DRILLS, key=lambda d: d[0])
    chosen = [d for d in by_chapter
              if args.only is None or d[0] == args.only]
    failures = 0
    async with httpx2.AsyncClient(
        base_url=API, timeout=10
    ) as http:
        for chapter, name, fn in chosen:
            await reset(http)
            try:
                detail = await fn(http)
                result = "pass"
            except Exception as exc:  # noqa: BLE001
                detail = str(exc) or type(exc).__name__
                result = "FAIL"
                failures += 1
            print(f"ch{chapter:02d}  {result}  {name}:"
                  f" {detail}", flush=True)
        await reset(http)
    print(f"{len(chosen) - failures} of {len(chosen)}"
          " drills passed")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=int)
    sys.exit(asyncio.run(main(parser.parse_args())))
