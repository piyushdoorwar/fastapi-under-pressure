"""Place one order the way the storefront does.

    python tools/storefront.py --sku TAB-10-R

The storefront makes up an Idempotency-Key when the
customer clicks "Place order", waits 2 seconds for
the shop API, and if there's no answer sends the same
request, with the same key, once more.
"""

import argparse
import asyncio
import time
import uuid

import httpx2

TIMEOUT = 2.0
ATTEMPTS = 2


async def place_order(client, body, key):
    for attempt in range(1, ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            resp = await client.post(
                "/orders", json=body,
                headers={"Idempotency-Key": key},
                timeout=TIMEOUT,
            )
        except httpx2.TimeoutException:
            took = time.perf_counter() - start
            print(f"attempt {attempt}: timed out"
                  f" after {took:.1f} s")
            continue
        took = time.perf_counter() - start
        print(f"attempt {attempt}: {resp.status_code}"
              f" in {took:.1f} s {resp.text}")
        return resp
    print("gave up: Something went wrong")


async def main(args):
    body = {
        "lines": [{"sku": args.sku, "qty": 1}],
        "postcode": "94107",
        "email": args.email,
    }
    key = str(uuid.uuid4())
    print(f"Idempotency-Key: {key}")
    async with httpx2.AsyncClient(
        base_url=args.url
    ) as client:
        await place_order(client, body, key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", default="TAB-10-R")
    parser.add_argument(
        "--email", default="sam@example.com"
    )
    parser.add_argument(
        "--url", default="http://localhost:8000"
    )
    asyncio.run(main(parser.parse_args()))
