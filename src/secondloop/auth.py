"""Customer sign-in for the account pages.

The identity provider signs short-lived tokens (RS256,
five minutes) and publishes its public keys as a JWKS.
The shop API checks each token with those keys.

Keys change (chapter 15). The provider can start
signing with a new key at any time, so the API keeps
its copy of the keys for at most `idp_keys_ttl_s` and
fetches them again, at most once per
`idp_refresh_cooldown_s`, when a token names a key it
doesn't have. Clocks differ, so times in the token are
checked with `idp_leeway_s` of slack.
"""

import asyncio
import json
import time
from typing import Annotated, Any

import httpx2
import jwt
import structlog
from fastapi import (
    Depends,
    Header,
    HTTPException,
    Request,
)
from jwt.algorithms import RSAAlgorithm
from prometheus_client import Counter

from secondloop.settings import settings

log = structlog.get_logger()
ISSUER = "https://id.secondloop.example"
AUDIENCE = "shop-api"
REJECTED = Counter(
    "auth_rejections_total",
    "Account requests refused, by reason",
    ["reason"],
)


def make_idp_http() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=settings.idp_url, timeout=2.0
    )


class KeyCache:
    """The provider's public keys, by key ID."""

    def __init__(self, http: httpx2.AsyncClient):
        self.http = http
        self.keys: dict[str, Any] = {}
        self.fetched_at = float("-inf")
        self.lock = asyncio.Lock()

    async def get(self, kid: str | None):
        age = time.monotonic() - self.fetched_at
        if age > settings.idp_keys_ttl_s or (
            kid not in self.keys
            and age > settings.idp_refresh_cooldown_s
        ):
            await self.refresh()
        return self.keys.get(kid)

    async def refresh(self) -> None:
        async with self.lock:  # one fetch at a time
            age = time.monotonic() - self.fetched_at
            if age < settings.idp_refresh_cooldown_s:
                return  # someone else just fetched them
            try:
                resp = await self.http.get(
                    "/.well-known/jwks.json"
                )
                resp.raise_for_status()
                self.keys = {
                    k["kid"]: RSAAlgorithm.from_jwk(
                        json.dumps(k)
                    )
                    for k in resp.json()["keys"]
                }
                log.info("idp_keys_fetched",
                         kids=sorted(self.keys))
            except (httpx2.HTTPError, ValueError,
                    KeyError) as exc:
                # Keep the keys we have; try again later.
                log.warning("idp_keys_fetch_failed",
                            error=type(exc).__name__)
            self.fetched_at = time.monotonic()


def refuse(reason: str) -> HTTPException:
    REJECTED.labels(reason).inc()
    log.info("auth_rejected", reason=reason)
    return HTTPException(
        401, "invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_customer(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """The signed-in customer's email address."""
    header = authorization or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise refuse("missing")
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise refuse("malformed") from exc
    key = await request.app.state.idp_keys.get(kid)
    if key is None:
        raise refuse("unknown_key")
    try:
        claims = jwt.decode(
            token, key, algorithms=["RS256"],
            audience=AUDIENCE, issuer=ISSUER,
            leeway=settings.idp_leeway_s,
        )
    except jwt.ExpiredSignatureError as exc:
        raise refuse("expired") from exc
    except jwt.ImmatureSignatureError as exc:
        raise refuse("not_yet_valid") from exc
    except jwt.PyJWTError as exc:
        raise refuse("invalid") from exc
    return claims["email"]


Customer = Annotated[str, Depends(current_customer)]
