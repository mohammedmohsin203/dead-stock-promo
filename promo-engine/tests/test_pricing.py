import pytest


@pytest.fixture(scope="module")
def priced(dataset):
    from engine.config import load_rules
    from engine.loader import load_catalog

    rules = load_rules()
    return load_catalog(rules), rules


def test_honey_gets_25_percent(priced):
    from engine.pricing import price_promo

    catalog, rules = priced
    promo = price_promo(catalog.loc["HNY500"], rules)
    assert promo["discount_pct"] == 25
    assert promo["new_price"] == 337.50
    assert promo["code"] == "DEAD25-HNY500"


def test_thin_margin_milk_is_capped_by_floor(priced):
    from engine.pricing import price_promo

    catalog, rules = priced
    promo = price_promo(catalog.loc["MLK1L"], rules)
    assert promo is None or promo["discount_pct"] <= 8


def test_fast_mover_gets_no_promo(priced):
    from engine.pricing import price_promo

    catalog, rules = priced
    assert price_promo(catalog.loc["GT100"], rules) is None


def test_margin_floor_and_cap_hold_for_every_product(priced):
    from engine.pricing import price_promo

    catalog, rules = priced
    promos = [(p, price_promo(p, rules)) for _, p in catalog.iterrows()]
    assert any(promo for _, promo in promos)
    for product, promo in promos:
        if promo is None:
            continue
        assert promo["new_price"] >= product["cost"] * (1 + rules["min_margin_pct"] / 100)
        assert 5 <= promo["discount_pct"] <= rules["max_discount_pct"]


def test_cart_discount_limited_to_max_units(priced):
    from engine.pricing import price_cart

    catalog, rules = priced
    offer = {"target_sku": "HNY500", "new_price": 337.50}
    totals = price_cart({"HNY500": 3}, catalog, offer, rules)
    assert totals["subtotal"] == 1350.00
    assert totals["discount"] == 225.00
    assert totals["final_total"] == 1125.00
