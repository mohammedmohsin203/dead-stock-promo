import csv

GREEN_TEA = [{"sku": "GT100", "qty": 1}]
TEA_AND_HONEY = [{"sku": "GT100", "qty": 1}, {"sku": "HNY500", "qty": 1}]
CODE = "DEAD25-HNY500"


def stock_on_disk(dataset, sku):
    with (dataset / "inventory.csv").open(newline="", encoding="utf-8") as f:
        return next(int(row["stock"]) for row in csv.DictReader(f) if row["sku"] == sku)


def test_green_tea_cart_recommends_honey(client):
    offer = client.post("/recommend", json={"items": GREEN_TEA}).json()["offer"]
    assert offer["target_sku"] == "HNY500"
    assert offer["discount_pct"] == 25
    assert offer["new_price"] == 337.50
    assert offer["code"] == CODE


def test_sugar_free_in_cart_blocks_honey(client):
    items = GREEN_TEA + [{"sku": "SF100", "qty": 1}]
    offer = client.post("/recommend", json={"items": items}).json()["offer"]
    assert offer is None or offer["target_sku"] != "HNY500"


def test_same_category_substitute_is_never_offered(client):
    offers = [o for o in client.get("/promos").json() if o["trigger_sku"] == "GT100"]
    assert offers
    assert "TULSI" not in {o["target_sku"] for o in offers}


def test_apply_valid_code_gives_server_totals(client):
    body = client.post("/cart/apply", json={"items": TEA_AND_HONEY, "code": CODE}).json()
    assert body["subtotal"] == 670.00
    assert body["discount"] == 112.50
    assert body["final_total"] == 557.50
    assert body["applied_code"] == CODE


def test_client_sent_prices_are_ignored(client):
    items = [{"sku": "GT100", "qty": 1, "price": 1}, {"sku": "HNY500", "qty": 1, "unit_price": 1}]
    body = client.post("/cart/apply", json={"items": items, "code": CODE}).json()
    assert body["final_total"] == 557.50


def test_code_needs_its_target_in_cart(client):
    response = client.post("/cart/apply", json={"items": GREEN_TEA, "code": CODE})
    assert response.status_code == 400
    assert "Organic Honey" in response.json()["detail"]


def test_quantity_over_stock_is_rejected(client):
    response = client.post("/cart/apply", json={"items": [{"sku": "HNY500", "qty": 99}]})
    assert response.status_code == 400


def test_expired_code_is_rejected(client, monkeypatch):
    from api.main import STATE

    monkeypatch.setitem(STATE.codes, CODE, {**STATE.codes[CODE], "expires_at": "2020-01-01T00:00:00+05:30"})
    response = client.post("/cart/apply", json={"items": TEA_AND_HONEY, "code": CODE})
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_tampered_cart_is_rejected_at_confirm(client, dataset):
    token = client.post("/cart/apply", json={"items": TEA_AND_HONEY, "code": CODE}).json()["token"]
    before = stock_on_disk(dataset, "HNY500")
    tampered = [{"sku": "GT100", "qty": 1}, {"sku": "HNY500", "qty": 5}]
    response = client.post("/order/confirm", json={"items": tampered, "token": token})
    assert response.status_code == 400
    assert stock_on_disk(dataset, "HNY500") == before


def test_forged_token_is_rejected(client):
    response = client.post("/order/confirm", json={"items": TEA_AND_HONEY, "token": "not.a.token"})
    assert response.status_code == 400


def test_confirm_decrements_stock_exactly_once(client, dataset):
    before = stock_on_disk(dataset, "HNY500")
    token = client.post("/cart/apply", json={"items": TEA_AND_HONEY, "code": CODE}).json()["token"]

    first = client.post("/order/confirm", json={"items": TEA_AND_HONEY, "token": token}).json()
    second = client.post("/order/confirm", json={"items": TEA_AND_HONEY, "token": token}).json()

    assert first["paid_total"] == 557.50
    assert first["stock_after"]["HNY500"] == before - 1
    assert second == first
    assert stock_on_disk(dataset, "HNY500") == before - 1
