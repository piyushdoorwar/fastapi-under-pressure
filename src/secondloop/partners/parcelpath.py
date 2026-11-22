"""ParcelPath rate client.

One AsyncClient is created at startup and shared by
every request, so connections to ParcelPath are
reused and nothing here blocks the event loop.
"""

from dataclasses import dataclass

import httpx2
from fastapi import Request

from secondloop.settings import settings


@dataclass
class Rate:
    service: str
    amount_cents: int
    eta_days: int


class ParcelPathClient:
    def __init__(self, http: httpx2.AsyncClient):
        self.http = http

    async def get_rate(
        self, weight_grams: int, postcode: str
    ) -> Rate:
        resp = await self.http.post(
            "/v1/rates",
            json={
                "weight_grams": weight_grams,
                "postcode": postcode,
            },
        )
        resp.raise_for_status()
        return Rate(**resp.json())


def make_http() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=settings.parcelpath_url,
        timeout=settings.parcelpath_timeout_s,
        limits=httpx2.Limits(max_connections=100),
    )


def get_parcelpath(request: Request) -> ParcelPathClient:
    return request.app.state.parcelpath
