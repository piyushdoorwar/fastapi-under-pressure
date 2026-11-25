"""A stand-in for the platform's load balancer.

The storefront never talks to an API process directly:
it talks to the balancer on port 8000, which forwards
each request to a healthy backend. The balancer checks
every backend's health path twice a second and only
sends traffic to backends that answer 200.

    BALANCER_BACKENDS=http://127.0.0.1:8001 \\
        uvicorn fakes.balancer:app --port 8000

    GET /_lb/backends               who is healthy
    PUT /_lb/backends ["http://..."]  replace the list
"""

import asyncio
import itertools
import os
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

HEALTH = os.getenv("BALANCER_HEALTH", "/healthz")
INTERVAL = 0.5
BACKENDS: dict[str, bool] = dict.fromkeys(
    os.getenv(
        "BALANCER_BACKENDS", "http://127.0.0.1:8001"
    ).split(","),
    False,
)
TURN = itertools.count()
HOP = {"host", "content-length", "connection",
       "transfer-encoding", "keep-alive"}


async def check(client: httpx2.AsyncClient) -> None:
    while True:
        for url in list(BACKENDS):
            try:
                resp = await client.get(
                    url + HEALTH, timeout=0.5
                )
                ok = resp.status_code == 200
            except httpx2.HTTPError:
                ok = False
            if url in BACKENDS:
                BACKENDS[url] = ok
        await asyncio.sleep(INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx2.AsyncClient(timeout=10) as client:
        app.state.client = client
        task = asyncio.create_task(check(client))
        yield
        task.cancel()


app = FastAPI(title="Balancer (fake)", lifespan=lifespan)


@app.get("/_lb/backends")
async def backends() -> dict[str, bool]:
    return BACKENDS


@app.put("/_lb/backends")
async def set_backends(urls: list[str]) -> dict:
    for url in list(BACKENDS):
        if url not in urls:
            del BACKENDS[url]
    for url in urls:
        BACKENDS.setdefault(url, False)
    return BACKENDS


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def forward(path: str, request: Request):
    healthy = [u for u, ok in BACKENDS.items() if ok]
    if not healthy:
        return JSONResponse(
            {"error": "no healthy backend"}, 502
        )
    url = healthy[next(TURN) % len(healthy)]
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in HOP}
    try:
        upstream = await request.app.state.client.request(
            request.method, f"{url}/{path}",
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        )
    except httpx2.HTTPError as exc:
        return JSONResponse(
            {"error": type(exc).__name__}, 502
        )
    return Response(
        upstream.content, upstream.status_code,
        headers={k: v for k, v in upstream.headers.items()
                 if k.lower() not in HOP
                 and k.lower() != "content-encoding"},
    )
