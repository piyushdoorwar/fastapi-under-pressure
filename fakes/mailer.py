"""A stand-in for SecondLoop's email provider.

It accepts messages, keeps them in memory, and lets
you read them back, so you can see exactly which
emails the shop API sent.

    GET    /v1/messages?to=...   list messages
    DELETE /v1/messages          forget them all
    PUT    /_fake/mode           {"status": 503}
    PUT    /_fake/mode           {"delay_ms": 1900}

Like the real provider, it answers 422 for an address
it can't deliver to (here: a domain without a dot), and
it honours an Idempotency-Key header: a second message
with the same key is not sent again, and the first
one's answer is returned instead.
"""

import asyncio
import itertools

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

MESSAGES: list[dict] = []
MODE = {"status": 202, "delay_ms": 0}
IDS = itertools.count(1)
BY_KEY: dict[str, dict] = {}

app = FastAPI(title="Mailer (fake)")


class MessageIn(BaseModel):
    to: str
    subject: str
    body: str


class ModeIn(BaseModel):
    status: int = 202
    delay_ms: int = 0


@app.post("/v1/messages")
async def send(
    msg: MessageIn,
    key: str | None = Header(
        None, alias="Idempotency-Key"
    ),
):
    if key in BY_KEY:  # seen it: don't send it again
        return JSONResponse(BY_KEY[key], status_code=202)
    stored = {"id": next(IDS), **msg.model_dump()}
    if key:
        BY_KEY[key] = stored  # claimed from arrival
    await asyncio.sleep(MODE["delay_ms"] / 1000)
    error, status = None, 202
    if MODE["status"] != 202:
        error, status = "unavailable", MODE["status"]
    elif "." not in msg.to.rpartition("@")[2]:
        error, status = "undeliverable address", 422
    if error:
        BY_KEY.pop(key, None)
        return JSONResponse({"error": error}, status)
    MESSAGES.append(stored)
    return JSONResponse(stored, status_code=202)


@app.get("/v1/messages")
async def list_messages(to: str | None = None):
    return [m for m in MESSAGES
            if to is None or m["to"] == to]


@app.delete("/v1/messages", status_code=204)
async def clear() -> None:
    MESSAGES.clear()
    BY_KEY.clear()


@app.put("/_fake/mode")
async def set_mode(body: ModeIn) -> dict:
    MODE.update(body.model_dump())
    return MODE
