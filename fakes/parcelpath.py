"""A stand-in for the ParcelPath rates API.

It answers like the real service and takes a
configurable time to do it, so you can test what
SecondLoop does when a partner is slow.
"""

import asyncio
import os
import random

from fastapi import FastAPI
from pydantic import BaseModel

DELAY_MS = int(os.getenv("PARCELPATH_DELAY_MS", "180"))
JITTER_MS = int(os.getenv("PARCELPATH_JITTER_MS", "40"))

app = FastAPI(title="ParcelPath (fake)")


class RateIn(BaseModel):
    weight_grams: int
    postcode: str


@app.post("/v1/rates")
async def rates(body: RateIn) -> dict:
    jitter = random.uniform(-JITTER_MS, JITTER_MS)
    await asyncio.sleep((DELAY_MS + jitter) / 1000)
    kilos = max(1, -(-body.weight_grams // 1000))
    return {
        "service": "ground",
        "amount_cents": 499 + 150 * kilos,
        "eta_days": 3,
    }
