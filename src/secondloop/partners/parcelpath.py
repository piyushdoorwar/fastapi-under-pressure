"""ParcelPath rate client.

One AsyncClient is created at startup and shared by
every request. Every call has a time budget and goes
through a circuit breaker, so a slow or failing
ParcelPath costs a quote at most one budget, and
usually nothing at all.
"""

import asyncio
from dataclasses import dataclass

import httpx2
import structlog
from fastapi import Request
from prometheus_client import Counter, Gauge
from pydantic import BaseModel

from secondloop.partners.breaker import CircuitBreaker
from secondloop.settings import settings

log = structlog.get_logger()

CALLS = Counter(
    "parcelpath_calls_total",
    "Calls to ParcelPath by outcome",
    ["outcome"],
)
BREAKER_OPEN = Gauge(
    "parcelpath_breaker_open",
    "1 while the ParcelPath breaker refuses calls",
)


@dataclass
class Rate:
    service: str
    amount_cents: int
    eta_days: int


class RateIn(BaseModel):
    """A rate as ParcelPath sends it. ParcelPath v1.4
    adds `amount`, in dollars, and drops `amount_cents`.
    This reads both, so the switch needs no deploy."""

    service: str
    eta_days: int
    amount_cents: int = 0  # gone in v1.4
    amount: float | None = None  # new in v1.4

    def to_rate(self) -> Rate:
        cents = self.amount_cents
        if self.amount is not None:
            cents = int(self.amount * 100)
        return Rate(self.service, cents, self.eta_days)


class PartnerUnavailable(Exception):
    """ParcelPath didn't give us a rate in time."""


class ParcelPathClient:
    def __init__(
        self,
        http: httpx2.AsyncClient,
        breaker: CircuitBreaker,
        budget_s: float,
    ):
        self.http = http
        self.breaker = breaker
        self.budget_s = budget_s

    async def get_rate(
        self, weight_grams: int, postcode: str
    ) -> Rate:
        if not self.breaker.allow():
            CALLS.labels("short_circuit").inc()
            raise PartnerUnavailable("breaker open")
        try:
            async with asyncio.timeout(self.budget_s):
                resp = await self.http.post(
                    "/v1/rates",
                    json={
                        "weight_grams": weight_grams,
                        "postcode": postcode,
                    },
                )
                resp.raise_for_status()
                rate = RateIn.model_validate(
                    resp.json()
                ).to_rate()
        except (TimeoutError, httpx2.HTTPError) as exc:
            outcome = (
                "timeout" if isinstance(exc, TimeoutError)
                else "error"
            )
            self._failed(outcome)
            raise PartnerUnavailable(outcome) from exc
        self._succeeded()
        return rate

    def _failed(self, outcome: str) -> None:
        CALLS.labels(outcome).inc()
        was = self.breaker.state
        self.breaker.record_failure()
        if self.breaker.state != was:
            BREAKER_OPEN.set(1)
            log.warning("parcelpath_breaker_open")

    def _succeeded(self) -> None:
        CALLS.labels("ok").inc()
        was = self.breaker.state
        self.breaker.record_success()
        if self.breaker.state != was:
            BREAKER_OPEN.set(0)
            log.info("parcelpath_breaker_closed")


def make_http() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=settings.parcelpath_url,
        timeout=settings.parcelpath_timeout_s,
        limits=httpx2.Limits(max_connections=100),
    )


def make_client(http: httpx2.AsyncClient):
    breaker = CircuitBreaker(
        failures=settings.parcelpath_breaker_failures,
        reset_after_s=settings.parcelpath_breaker_reset_s,
    )
    return ParcelPathClient(
        http, breaker, settings.parcelpath_budget_s
    )


def get_parcelpath(request: Request) -> ParcelPathClient:
    return request.app.state.parcelpath
