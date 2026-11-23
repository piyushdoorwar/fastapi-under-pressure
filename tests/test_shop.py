CART = {
    "lines": [
        {"sku": "LAP-14-R", "qty": 1},
        {"sku": "CHG-65-C", "qty": 1},
    ],
    "postcode": "94107",
}


async def test_lists_products(client):
    resp = await client.get("/products")
    assert resp.status_code == 200
    assert len(resp.json()) == 20


async def test_unknown_product_is_404(client):
    resp = await client.get("/products/NOPE")
    assert resp.status_code == 404


async def test_quote_adds_shipping(client, fixed_rate):
    resp = await client.post("/checkout/quote", json=CART)
    assert resp.status_code == 200
    body = resp.json()
    assert body["subtotal_cents"] == 64900 + 3900
    assert body["shipping_cents"] == 949
    assert body["total_cents"] == 68800 + 949


async def test_quote_rejects_unknown_sku(client):
    cart = {**CART, "lines": [{"sku": "NOPE", "qty": 1}]}
    resp = await client.post("/checkout/quote", json=cart)
    assert resp.status_code == 422
