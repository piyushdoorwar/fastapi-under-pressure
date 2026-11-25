"""Chapter 15 guardrails: sign-in keeps working when the
identity provider rotates its keys or its clock is a
few seconds out, and every rejection says why."""

import asyncio
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from tests.test_stock import set_stock


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def my_orders(client, token):
    return await client.get(
        "/account/orders", headers=bearer(token)
    )


async def status(client, token):
    return (await my_orders(client, token)).status_code


NOBODYS_KEY = rsa.generate_private_key(
    public_exponent=65537, key_size=2048
)


def forged(kid):
    """A token signed with a key nobody published."""
    key = NOBODYS_KEY
    now = int(time.time())
    return jwt.encode(
        {"sub": "x@example.com", "email": "x@example.com",
         "iat": now, "exp": now + 300},
        key, algorithm="RS256", headers={"kid": kid},
    )


async def test_customer_sees_own_orders(
    client, idp, inbox
):
    await set_stock("KBD-MX-R", reno=10)
    resp = await client.post("/orders", json={
        "lines": [{"sku": "KBD-MX-R", "qty": 1}],
        "postcode": "94107", "email": "ann@example.com",
    })
    number = resp.json()["number"]
    resp = await my_orders(
        client, await idp.token("ann@example.com")
    )
    assert resp.status_code == 200
    assert [o["number"] for o in resp.json()] == [number]
    other = await my_orders(
        client, await idp.token("bob@example.com")
    )
    assert other.json() == []


async def test_no_token_is_refused(client):
    resp = await client.get("/account/orders")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


async def test_new_signing_key_is_picked_up(client, idp):
    first = await idp.token("cat@example.com")
    assert await status(client, first) == 200
    await idp.mode(rotate=True)  # after we have its keys
    await asyncio.sleep(0.6)  # past the refresh cooldown
    token = await idp.token("cat@example.com")
    assert await status(client, token) == 200


async def test_clocks_a_few_seconds_apart(client, idp):
    await idp.mode(skew_s=5)  # the provider runs fast
    token = await idp.token("dee@example.com")
    assert await status(client, token) == 200


async def test_expired_token_is_refused(client, idp):
    token = await idp.token("eve@example.com", ttl_s=-60)
    assert await status(client, token) == 401


async def test_unknown_keys_do_not_flood_the_provider(
    client, idp
):
    before = (await idp.stats())["jwks_fetches"]
    for n in range(20):
        resp = await my_orders(client, forged(f"bad-{n}"))
        assert resp.status_code == 401
    after = (await idp.stats())["jwks_fetches"]
    assert after - before <= 2


async def test_rejections_say_why(client):
    await my_orders(client, forged("bad"))
    metrics = (await client.get("/metrics")).text
    line = 'auth_rejections_total{reason="unknown_key"}'
    assert line in metrics
