"""Chapter 11 guardrails: a ParcelPath answer is either
read exactly, or not used at all."""

import pytest

CART = {
    "lines": [{"sku": "LAP-14-R", "qty": 1},
              {"sku": "CHG-65-C", "qty": 1}],
    "postcode": "94107",
}
NINE_KILOS = {
    "lines": [{"sku": "LAP-14-R", "qty": 5}],
    "postcode": "94107",
}


async def quote(client, cart=CART):
    resp = await client.post("/checkout/quote", json=cart)
    assert resp.status_code == 200
    return resp.json()


async def test_v14_rate_is_read(client, partner):
    await partner(version="1.4")
    body = await quote(client)
    assert body["shipping_cents"] == 949
    assert body["shipping_estimated"] is False


async def test_v14_rate_is_exact(client, partner):
    await partner(version="1.4")
    body = await quote(client, NINE_KILOS)
    assert body["shipping_cents"] == 1849


@pytest.mark.parametrize("answer", [
    {"service": "ground", "eta_days": 3},
    {"service": "ground", "eta_days": 3,
     "price": {"amount": "9.49", "currency": "EUR"}},
    {"service": "ground", "eta_days": 3,
     "amount": 9.49},
])
async def test_unreadable_rate_is_not_used(
    client, partner, answer
):
    await partner(body=answer)
    body = await quote(client)
    assert body["shipping_estimated"] is True
    assert body["shipping_cents"] > 0


def test_every_price_converts_exactly():
    from secondloop.partners.parcelpath import parse_rate

    for cents in range(1, 20_001):
        dollars = f"{cents // 100}.{cents % 100:02d}"
        price = {"amount": dollars, "currency": "USD"}
        rate = parse_rate({
            "service": "ground", "eta_days": 3,
            "price": price,
        })
        assert rate.amount_cents == cents, dollars
