"""A stand-in for the ParcelPath rates API.

It answers like the real service and takes a
configurable time to do it, so you can test what
SecondLoop does when a partner is slow or down.

Start it with PARCELPATH_DELAY_MS and
PARCELPATH_JITTER_MS, or change its behaviour while
it runs:

    curl -X PUT localhost:8081/_fake/mode \\
      -H 'content-type: application/json' \\
      -d '{"delay_ms": 3000}'

"status" makes it answer with that HTTP status
instead of a rate, e.g. {"status": 503}.
"""

import asyncio
import os
import random

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

MODE = {
    "delay_ms": int(os.getenv("PARCELPATH_DELAY_MS", "180")),
    "jitter_ms": int(os.getenv("PARCELPATH_JITTER_MS", "40")),
    "status": 200,
}

app = FastAPI(title="ParcelPath (fake)")


class RateIn(BaseModel):
    weight_grams: int
    postcode: str


class ModeIn(BaseModel):
    delay_ms: int | None = None
    jitter_ms: int | None = None
    status: int | None = None


@app.post("/v1/rates")
async def rates(body: RateIn):
    jitter = random.uniform(
        -MODE["jitter_ms"], MODE["jitter_ms"]
    )
    await asyncio.sleep((MODE["delay_ms"] + jitter) / 1000)
    if MODE["status"] != 200:
        return JSONResponse(
            {"error": "rates unavailable"},
            status_code=MODE["status"],
        )
    kilos = max(1, -(-body.weight_grams // 1000))
    return {
        "service": "ground",
        "amount_cents": 499 + 150 * kilos,
        "eta_days": 3,
    }


@app.put("/_fake/mode")
async def set_mode(body: ModeIn) -> dict:
    MODE.update(body.model_dump(exclude_none=True))
    return MODE
