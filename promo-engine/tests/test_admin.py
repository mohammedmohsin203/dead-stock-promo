import pytest

GREEN_TEA = [{"sku": "GT100", "qty": 1}]


def honey_offer(client):
    return client.post("/recommend", json={"items": GREEN_TEA}).json()["offer"]


@pytest.fixture
def original_rules(client):
    rules = client.get("/admin/data").json()["rules"]
    yield rules
    assert client.put("/admin/rules", json=rules).status_code == 200


def test_admin_page_is_served(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Dead-stock Promo Engine" in response.text


def test_admin_data_shows_stock_and_current_promo(client):
    data = client.get("/admin/data").json()
    honey = next(p for p in data["products"] if p["sku"] == "HNY500")
    assert honey["is_dead"] is True
    assert honey["discount_pct"] == 25
    assert data["kpis"]["dead_products"] >= 15
    assert data["rules"]["discount_tiers"] == [
        {"days": 21, "pct": 10}, {"days": 30, "pct": 20}, {"days": 40, "pct": 25},
    ]


def test_offers_expose_score_breakdown(client):
    green_tea = next(o for o in client.get("/admin/offers").json() if o["trigger_sku"] == "GT100")
    top = green_tea["offers"][0]
    assert top["target_sku"] == "HNY500"
    assert top["explain"]["pairs_match"] is True
    assert top["tier_pct"] == 25
    assert top["floor_price"] == 330.00


def test_lowering_the_cap_reprices_offers(client, original_rules):
    response = client.put("/admin/rules", json={**original_rules, "max_discount_pct": 15})
    assert response.status_code == 200
    offer = honey_offer(client)
    assert offer["discount_pct"] == 15
    assert offer["new_price"] == 382.50
    assert offer["code"] == "DEAD15-HNY500"


def test_changing_a_tier_reprices_offers(client, original_rules):
    tiers = [{"days": 21, "pct": 10}, {"days": 40, "pct": 12}]
    assert client.put("/admin/rules", json={**original_rules, "discount_tiers": tiers}).status_code == 200
    assert honey_offer(client)["discount_pct"] == 12


def test_raising_the_margin_floor_limits_the_discount(client, original_rules):
    assert client.put("/admin/rules", json={**original_rules, "min_margin_pct": 30}).status_code == 200
    offer = honey_offer(client)
    assert offer is None or offer["target_sku"] != "HNY500" or offer["new_price"] >= 390.00


def test_rules_are_restored_after_edits(client):
    assert honey_offer(client)["discount_pct"] == 25


@pytest.mark.parametrize("change", [
    {"max_discount_pct": 95},
    {"near_expiry_days": 30},
    {"discount_tiers": []},
    {"discount_tiers": [{"days": 0, "pct": 10}]},
])
def test_invalid_rules_are_rejected(client, change):
    rules = client.get("/admin/data").json()["rules"]
    assert client.put("/admin/rules", json={**rules, **change}).status_code == 422
    assert client.get("/admin/data").json()["rules"] == rules


def test_order_appears_in_admin_feed_with_customer(client):
    token = client.post("/cart/apply", json={"items": GREEN_TEA}).json()["token"]
    order = client.post(
        "/order/confirm", json={"items": GREEN_TEA, "token": token, "customer": "asha@example.com"}
    ).json()

    data = client.get("/admin/data").json()
    latest = data["orders"][0]
    assert latest["order_id"] == order["order_id"]
    assert latest["customer"] == "asha@example.com"
    assert latest["items"] == [{"sku": "GT100", "name": "Green Tea 100g", "qty": 1}]
    assert data["kpis"]["revenue"] >= 220.00


def test_set_stock_updates_live_stock(client):
    assert client.post("/admin/stock", json={"sku": "SALT1", "stock": 7}).json() == {"sku": "SALT1", "stock": 7}
    salt = next(p for p in client.get("/admin/data").json()["products"] if p["sku"] == "SALT1")
    assert salt["stock"] == 7


def test_set_stock_rejects_unknown_sku_and_negative_values(client):
    assert client.post("/admin/stock", json={"sku": "NOPE", "stock": 5}).status_code == 404
    assert client.post("/admin/stock", json={"sku": "SALT1", "stock": -1}).status_code == 422
