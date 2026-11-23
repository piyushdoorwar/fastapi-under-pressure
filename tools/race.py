"""Send several orders for the same product at once.

    python tools/race.py --sku PHN-12-R --orders 8

Prints the status code of each order, then how many
were accepted. Run `make seed` first: PHN-12-R has
one unit left, in Dallas.
"""

import argparse
import asyncio
from collections import Counter

import httpx2


def cart(sku: str, n: int) -> dict:
    return {
        "lines": [{"sku": sku, "qty": 1}],
        "postcode": "94107",
        "email": f"race{n}@example.com",
    }


async def main(args):
    async with httpx2.AsyncClient(
        base_url=args.url, timeout=10
    ) as client:
        replies = await asyncio.gather(*(
            client.post("/orders", json=cart(args.sku, n))
            for n in range(args.orders)
        ))
    codes = [r.status_code for r in replies]
    print(" ".join(map(str, codes)))
    print(dict(sorted(Counter(codes).items())))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sku", default="PHN-12-R")
    parser.add_argument("--orders", type=int, default=8)
    parser.add_argument(
        "--url", default="http://localhost:8000"
    )
    asyncio.run(main(parser.parse_args()))
