"""A stand-in for SecondLoop's email provider.

It accepts messages, keeps them in memory, and lets
you read them back, so you can see exactly which
emails the shop API sent.

    GET    /v1/messages?to=...   list messages
    DELETE /v1/messages          forget them all
    PUT    /_fake/mode           {"status": 503}
"""

import itertools

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

MESSAGES: list[dict] = []
MODE = {"status": 202}
IDS = itertools.count(1)

app = FastAPI(title="Mailer (fake)")


class MessageIn(BaseModel):
    to: str
    subject: str
    body: str


class ModeIn(BaseModel):
    status: int


@app.post("/v1/messages")
async def send(msg: MessageIn):
    if MODE["status"] != 202:
        return JSONResponse(
            {"error": "unavailable"},
            status_code=MODE["status"],
        )
    stored = {"id": next(IDS), **msg.model_dump()}
    MESSAGES.append(stored)
    return JSONResponse(stored, status_code=202)


@app.get("/v1/messages")
async def list_messages(to: str | None = None):
    return [m for m in MESSAGES
            if to is None or m["to"] == to]


@app.delete("/v1/messages", status_code=204)
async def clear() -> None:
    MESSAGES.clear()


@app.put("/_fake/mode")
async def set_mode(body: ModeIn) -> dict:
    MODE.update(body.model_dump())
    return MODE
