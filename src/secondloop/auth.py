"""Customer sign-in for the account pages.

The identity provider signs short-lived tokens (RS256,
five minutes). The shop API checks them with the
provider's public keys, which it fetches once at startup
so that no request ever waits for the provider.
"""

import json
from typing import Annotated

import httpx2
import jwt
from fastapi import (
    Depends,
    Header,
    HTTPException,
    Request,
)
from jwt.algorithms import RSAAlgorithm

from secondloop.settings import settings

ISSUER = "https://id.secondloop.example"
AUDIENCE = "shop-api"


def make_idp_http() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=settings.idp_url, timeout=2.0
    )


async def load_keys(http: httpx2.AsyncClient) -> dict:
    resp = await http.get("/.well-known/jwks.json")
    resp.raise_for_status()
    return {
        k["kid"]: RSAAlgorithm.from_jwk(json.dumps(k))
        for k in resp.json()["keys"]
    }


def unauthorized() -> HTTPException:
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
        raise unauthorized()
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        key = request.app.state.idp_keys.get(kid)
        if key is None:
            raise unauthorized()
        claims = jwt.decode(
            token, key, algorithms=["RS256"],
            audience=AUDIENCE, issuer=ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise unauthorized() from exc
    return claims["email"]


Customer = Annotated[str, Depends(current_customer)]
