"""ParcelPath rate client.

One AsyncClient is created at startup and shared by
every request. Every call has a time budget and goes
through a circuit breaker, so a slow or failing
ParcelPath costs a quote at most one budget, and
usually nothing at all.
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import httpx2
import structlog
from fastapi import Request
from prometheus_client import Counter, Gauge
from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
)

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


class RateV13(BaseModel):
    """ParcelPath's answer up to v1.3."""

    service: str
    amount_cents: int = Field(ge=0)
    eta_days: int = Field(ge=1, le=30)

    def to_rate(self) -> Rate:
        return Rate(
            self.service, self.amount_cents, self.eta_days
        )


class Price(BaseModel):
    amount: Decimal = Field(ge=0, decimal_places=2)
    currency: Literal["USD"]


class RateV14(BaseModel):
    """ParcelPath's answer from v1.4 (23 November)."""

    service: str
    price: Price
    eta_days: int = Field(ge=1, le=30)

    def to_rate(self) -> Rate:
        cents = int(self.price.amount * 100)
        return Rate(self.service, cents, self.eta_days)


# Every field is required: an answer that is missing
# one is not a rate, whatever else it contains.
RATE = TypeAdapter(RateV14 | RateV13)


class BadRate(ValueError):
    """ParcelPath answered with something that isn't a
    rate we understand."""


def parse_rate(data: object) -> Rate:
    try:
        return RATE.validate_python(data).to_rate()
    except ValidationError as exc:
        raise BadRate(str(exc)) from exc


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
                rate = parse_rate(resp.json())
        except (TimeoutError, httpx2.HTTPError) as exc:
            outcome = (
                "timeout" if isinstance(exc, TimeoutError)
                else "error"
            )
            self._failed(outcome)
            raise PartnerUnavailable(outcome) from exc
        except ValueError as exc:
            # BadRate, or a body that isn't JSON at all.
            log.warning("parcelpath_bad_rate",
                        error=str(exc)[:200])
            self._failed("bad_rate")
            raise PartnerUnavailable("bad_rate") from exc
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
