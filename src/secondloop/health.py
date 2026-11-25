"""Health checks for the platform (chapter 14).

/healthz is liveness: "is this process able to answer at
all?" If it fails, the platform restarts the process.
It must not depend on anything outside the process, or a
database outage would restart every healthy API process.

/readyz is readiness: "should the balancer send this
process traffic right now?" It fails while the process
is draining before shutdown, and when the database
can't be reached.
"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from secondloop.db import engine

router = APIRouter()


async def database_ok() -> bool:
    try:
        async with asyncio.timeout(0.5):
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
    except (TimeoutError, OSError, SQLAlchemyError):
        return False
    return True


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    if request.app.state.draining:
        return JSONResponse({"status": "draining"}, 503)
    if not await database_ok():
        return JSONResponse({"status": "no db"}, 503)
    return {"status": "ready"}
