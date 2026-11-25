"""A stand-in for SecondLoop's identity provider.

    uvicorn fakes.idp:app --port 8083

    GET  /.well-known/jwks.json      the public keys
    POST /token {"email": "..."}     a five-minute token
    PUT  /_fake/mode {"rotate": true}   start signing
                                     with a new key
    PUT  /_fake/mode {"skew_s": 5}   pretend our clock
                                     is 5 seconds fast
    PUT  /_fake/mode {"reset": true}
    GET  /_fake/stats                how often the JWKS
                                     was fetched

Like a well-behaved provider, it keeps publishing the
old key after a rotation, so tokens already issued stay
valid until they expire.
"""

import itertools
import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

ISSUER = "https://id.secondloop.example"
AUDIENCE = "shop-api"
KIDS = (f"key-{n}" for n in itertools.count(1))


def new_key() -> tuple[str, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )
    return next(KIDS), key


FIRST = new_key()
STATE = {"keys": [FIRST], "skew_s": 0, "fetches": 0}
app = FastAPI(title="Identity provider (fake)")


class TokenIn(BaseModel):
    email: str
    ttl_s: int = 300


class ModeIn(BaseModel):
    rotate: bool = False
    skew_s: int | None = None
    reset: bool = False


@app.get("/.well-known/jwks.json")
async def jwks() -> dict:
    STATE["fetches"] += 1
    keys = []
    for kid, key in STATE["keys"]:
        jwk = json.loads(RSAAlgorithm.to_jwk(
            key.public_key()
        ))
        keys.append({**jwk, "kid": kid, "alg": "RS256",
                     "use": "sig"})
    return {"keys": keys}


@app.post("/token")
async def token(body: TokenIn) -> dict:
    kid, key = STATE["keys"][-1]
    now = int(time.time()) + STATE["skew_s"]
    claims = {
        "iss": ISSUER, "aud": AUDIENCE,
        "sub": body.email, "email": body.email,
        "iat": now, "nbf": now, "exp": now + body.ttl_s,
    }
    signed = jwt.encode(claims, key, algorithm="RS256",
                        headers={"kid": kid})
    return {"access_token": signed, "kid": kid}


@app.put("/_fake/mode")
async def set_mode(body: ModeIn) -> dict:
    if body.reset:
        STATE.update(keys=[FIRST], skew_s=0, fetches=0)
    if body.rotate:
        STATE["keys"].append(new_key())
    if body.skew_s is not None:
        STATE["skew_s"] = body.skew_s
    return await stats()


@app.get("/_fake/stats")
async def stats() -> dict:
    return {
        "kids": [kid for kid, _ in STATE["keys"]],
        "skew_s": STATE["skew_s"],
        "jwks_fetches": STATE["fetches"],
    }
