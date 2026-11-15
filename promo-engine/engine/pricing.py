from datetime import datetime, timedelta

from .config import IST

MIN_PROMO_PCT = 5


def money(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def tier_pct(days_unsold: int, days_to_expiry: int, rules: dict) -> int:
    """Discount before the cap and margin floor: the expiry discount wins, else the highest tier reached."""
    if days_to_expiry <= rules["expiry_discount_days"]:
        return rules["expiry_discount_pct"]
    return max((t["pct"] for t in rules["discount_tiers"] if days_unsold >= t["days"]), default=0)


def price_promo(product, rules: dict, now: datetime | None = None) -> dict | None:
    """Margin-safe discount for one product, or None if no promo of >= 5% is possible."""
    price, cost = float(product["price"]), float(product["cost"])
    floor = cost * (1 + rules["min_margin_pct"] / 100)
    tier = tier_pct(int(product["days_unsold"]), int(product["days_to_expiry"]), rules)
    pct = min(tier, rules["max_discount_pct"])
    while pct >= MIN_PROMO_PCT and money(price * (1 - pct / 100)) < floor:
        pct -= 1
    if pct < MIN_PROMO_PCT:
        return None
    now = now or datetime.now(IST)
    expires_at = (now + timedelta(hours=rules["promo_valid_hours"])).astimezone(IST)
    return {
        "discount_pct": pct,
        "price": money(price),
        "new_price": money(price * (1 - pct / 100)),
        "code": f"DEAD{pct}-{product['sku']}",
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "tier_pct": tier,
        "floor_price": money(floor),
    }


def price_cart(items: dict[str, int], catalog, offer: dict | None, rules: dict) -> dict:
    """Server-side cart totals. items maps sku -> qty; offer discounts up to max_discounted_units."""
    lines = []
    subtotal = discount = 0.0
    for sku, qty in items.items():
        unit_price = float(catalog.loc[sku, "price"])
        line_discount = 0.0
        if offer and sku == offer["target_sku"]:
            units = min(qty, rules["max_discounted_units"])
            line_discount = units * (unit_price - offer["new_price"])
        subtotal += unit_price * qty
        discount += line_discount
        lines.append({
            "sku": sku,
            "name": catalog.loc[sku, "name"],
            "qty": qty,
            "unit_price": money(unit_price),
            "line_total": money(unit_price * qty - line_discount),
            "discount": money(line_discount),
        })
    return {
        "lines": lines,
        "subtotal": money(subtotal),
        "discount": money(discount),
        "final_total": money(subtotal - discount),
    }
