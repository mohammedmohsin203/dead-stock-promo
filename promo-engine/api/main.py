import csv
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime

import jwt
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import llm, recommend, signing
from engine.config import IST, ROOT, cache_dir, data_dir, load_rules, save_rules, write_atomic
from engine.loader import load_catalog
from engine.pricing import price_cart

logging.basicConfig(level=logging.WARNING)
logging.getLogger("engine").setLevel(logging.INFO)
LOG_COLUMNS = ["order_id", "order_ref", "code", "paid_total", "items", "created_at", "customer", "discount"]
ADMIN_ORDER_LIMIT = 100


class State:
    rules: dict
    catalog: pd.DataFrame
    promos: dict
    codes: dict[str, dict]

    def reload_catalog(self) -> None:
        self.rules = load_rules()
        self.catalog = load_catalog(self.rules)

    def set_promos(self, promos: dict) -> None:
        self.promos = promos
        self.codes = {o["code"]: o for offers in promos["offers"].values() for o in offers}


STATE = State()
# ponytail: one process-wide lock around every CSV/JSON write; move to a database if this ever needs throughput.
LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    STATE.reload_catalog()
    STATE.set_promos(recommend.load_promos() or recommend.rebuild())
    yield


app = FastAPI(title="Dead-stock Promo Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({"http://localhost:3000", "http://127.0.0.1:3000",
                          os.getenv("STORE_ORIGIN", "http://localhost:3000")}),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/widget", StaticFiles(directory=ROOT / "widget"), name="widget")


class CartItem(BaseModel):
    sku: str
    qty: int = Field(ge=1, le=99)


class CartRequest(BaseModel):
    items: list[CartItem]


class ApplyRequest(CartRequest):
    code: str | None = None


class ConfirmRequest(CartRequest):
    token: str
    customer: str | None = Field(default=None, max_length=200)


class Health(BaseModel):
    status: str


class StoreProduct(BaseModel):
    sku: str
    name: str
    category: str
    price: float
    stock: int
    image: str


class Offer(BaseModel):
    trigger_sku: str
    target_sku: str
    target_name: str
    image: str
    price: float
    new_price: float
    discount_pct: int
    code: str
    message: str
    reason: str
    expires_at: str


class RecommendResponse(BaseModel):
    offer: Offer | None


class RebuildResponse(BaseModel):
    offers: int
    took_ms: int


class CartLine(BaseModel):
    sku: str
    name: str
    qty: int
    unit_price: float
    line_total: float
    discount: float


class ApplyResponse(BaseModel):
    lines: list[CartLine]
    subtotal: float
    discount: float
    final_total: float
    applied_code: str | None
    token: str


class ConfirmResponse(BaseModel):
    order_id: str
    paid_total: float
    stock_after: dict[str, int]


class DiscountTier(BaseModel):
    days: int = Field(ge=1, le=365)
    pct: int = Field(ge=5, le=90)


class Rules(BaseModel):
    min_margin_pct: int = Field(ge=0, le=200)
    max_discount_pct: int = Field(ge=5, le=90)
    dead_stock_days: int = Field(ge=1, le=365)
    # Below 30: the stuck score scales expiry urgency between this value and 30 days.
    near_expiry_days: int = Field(ge=0, le=29)
    promo_valid_hours: int = Field(ge=1, le=720)
    max_uses_per_code: int = Field(ge=1, le=100000)
    max_discounted_units: int = Field(ge=1, le=99)
    expiry_discount_days: int = Field(ge=0, le=30)
    expiry_discount_pct: int = Field(ge=5, le=90)
    discount_tiers: list[DiscountTier] = Field(min_length=1, max_length=6)


class StockUpdate(BaseModel):
    sku: str
    stock: int = Field(ge=0, le=100000)


class StockResponse(BaseModel):
    sku: str
    stock: int


def cart_dict(items: list[CartItem]) -> dict[str, int]:
    """Merged sku -> qty. Rejects empty carts and unknown SKUs; client prices are never read."""
    cart: dict[str, int] = {}
    for item in items:
        if item.sku not in STATE.catalog.index:
            raise HTTPException(400, f"Unknown product: {item.sku}")
        cart[item.sku] = cart.get(item.sku, 0) + item.qty
    if not cart:
        raise HTTPException(400, "Your cart is empty.")
    return cart


def check_stock(cart: dict[str, int]) -> None:
    for sku, qty in cart.items():
        stock = int(STATE.catalog.loc[sku, "stock"])
        if qty > stock:
            raise HTTPException(400, f"Only {stock} left of {STATE.catalog.loc[sku, 'name']}.")


def read_usage() -> dict[str, int]:
    path = cache_dir() / "usage.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_orders() -> list[dict]:
    path = cache_dir() / "orders_log.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_order(order: dict) -> None:
    path = cache_dir() / "orders_log.csv"
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
        if header != LOG_COLUMNS:
            # Log written before a column was added: rewrite it once with the current header.
            rows = read_orders()
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS, extrasaction="ignore", restval="")
                writer.writeheader()
                writer.writerows(rows)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(order)


def set_stock(changes: dict[str, int], relative: bool) -> None:
    """Write new stock levels to inventory.csv and refresh the in-memory catalog. Caller holds LOCK."""
    inventory = pd.read_csv(data_dir() / "inventory.csv", dtype={"sku": str})
    for sku, value in changes.items():
        row = inventory["sku"] == sku
        inventory.loc[row, "stock"] = inventory.loc[row, "stock"] + value if relative else value
    write_atomic(data_dir() / "inventory.csv", inventory.to_csv(index=False))
    STATE.reload_catalog()


@app.get("/health", response_model=Health)
def health():
    return {"status": "ok"}


@app.get("/store/products", response_model=list[StoreProduct])
def store_products():
    return STATE.catalog[["sku", "name", "category", "price", "stock", "image"]].to_dict("records")


@app.get("/promos", response_model=list[Offer])
def promos():
    return [o for offers in STATE.promos["offers"].values() for o in offers]


@app.post("/admin/rebuild", response_model=RebuildResponse)
def admin_rebuild():
    with LOCK:
        STATE.reload_catalog()
        STATE.set_promos(recommend.rebuild())
    return {"offers": len(STATE.promos["offers"]), "took_ms": STATE.promos["took_ms"]}


@app.post("/recommend", response_model=RecommendResponse)
def recommend_offer(body: CartRequest):
    cart = {i.sku: i.qty for i in body.items if i.sku in STATE.catalog.index}
    return {"offer": recommend.recommend_for_cart(cart, STATE.promos, STATE.catalog, STATE.rules)}


@app.post("/cart/apply", response_model=ApplyResponse)
def cart_apply(body: ApplyRequest):
    cart = cart_dict(body.items)
    check_stock(cart)
    code = (body.code or "").strip().upper() or None
    offer = None
    if code:
        offer = STATE.codes.get(code)
        if offer is None:
            raise HTTPException(400, f"Code {code} is not valid.")
        if datetime.fromisoformat(offer["expires_at"]) <= datetime.now(IST):
            raise HTTPException(400, f"Code {code} has expired.")
        if read_usage().get(code, 0) >= STATE.rules["max_uses_per_code"]:
            raise HTTPException(400, f"Code {code} has been fully redeemed.")
        if offer["target_sku"] not in cart:
            raise HTTPException(400, f"Add {offer['target_name']} to your cart to use {code}.")
    totals = price_cart(cart, STATE.catalog, offer, STATE.rules)
    token = signing.sign_totals(code, totals["final_total"], totals["discount"], cart)
    return {**totals, "applied_code": code, "token": token}


@app.post("/order/confirm", response_model=ConfirmResponse)
def order_confirm(body: ConfirmRequest):
    cart = cart_dict(body.items)
    try:
        payload = signing.verify_totals(body.token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(400, "Your totals expired. Please review your cart and try again.")
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Invalid payment token.")
    if payload["cart_hash"] != signing.cart_hash(cart):
        raise HTTPException(400, "Your cart changed after the total was calculated. Please review it again.")

    with LOCK:
        logged = next((o for o in read_orders() if o["order_ref"] == payload["order_ref"]), None)
        if logged is None:
            check_stock(cart)
            set_stock({sku: -qty for sku, qty in cart.items()}, relative=True)

            if payload["code"]:
                usage = read_usage()
                usage[payload["code"]] = usage.get(payload["code"], 0) + 1
                write_atomic(cache_dir() / "usage.json", json.dumps(usage, indent=2))

            logged = {
                "order_id": "GG-" + payload["order_ref"][:8].upper(),
                "order_ref": payload["order_ref"],
                "code": payload["code"] or "",
                "paid_total": payload["final_total"],
                "items": json.dumps(cart),
                "created_at": datetime.now(IST).isoformat(timespec="seconds"),
                "customer": (body.customer or "").strip(),
                "discount": payload.get("discount", "0.00"),
            }
            append_order(logged)
        stock_after = {sku: int(STATE.catalog.loc[sku, "stock"]) for sku in cart}
    return {"order_id": logged["order_id"], "paid_total": float(logged["paid_total"]), "stock_after": stock_after}


@app.get("/admin", response_class=FileResponse)
def admin():
    return FileResponse(ROOT / "admin" / "index.html")


@app.get("/admin/data")
def admin_data():
    """Everything the admin panel polls: live stock, orders, redemptions, KPIs and the current rules."""
    catalog = STATE.catalog
    promo_by_target = {o["target_sku"]: o for o in STATE.codes.values()}
    columns = ["sku", "name", "category", "price", "cost", "stock", "days_unsold", "days_to_expiry", "stuck", "is_dead"]
    products = json.loads(catalog[columns].to_json(orient="records"))
    for product in products:
        promo = promo_by_target.get(product["sku"])
        product["discount_pct"] = promo["discount_pct"] if promo else None
        product["new_price"] = promo["new_price"] if promo else None
        product["code"] = promo["code"] if promo else None

    names = catalog["name"].to_dict()
    orders = []
    for row in reversed(read_orders()):
        items = json.loads(row["items"])
        orders.append({
            "order_id": row["order_id"],
            "created_at": row["created_at"],
            "customer": row.get("customer") or "",
            "code": row["code"],
            "paid_total": float(row["paid_total"]),
            "discount": float(row.get("discount") or 0),
            "items": [{"sku": sku, "name": names.get(sku, sku), "qty": qty} for sku, qty in items.items()],
        })

    dead = catalog[catalog["is_dead"]]
    usage = read_usage()
    return {
        "kpis": {
            "products": len(catalog),
            "dead_products": len(dead),
            "dead_units": int(dead["stock"].sum()),
            "dead_value_at_cost": float((dead["stock"] * dead["cost"]).sum()),
            "orders": len(orders),
            "revenue": round(sum(o["paid_total"] for o in orders), 2),
            "discount_given": round(sum(o["discount"] for o in orders), 2),
            "promo_orders": sum(1 for o in orders if o["code"]),
            "customers": len({o["customer"] for o in orders if o["customer"]}),
        },
        "products": products,
        "orders": orders[:ADMIN_ORDER_LIMIT],
        "usage": [
            {"code": code, "used": used, "limit": STATE.rules["max_uses_per_code"],
             "target_name": STATE.codes[code]["target_name"] if code in STATE.codes else ""}
            for code, used in sorted(usage.items(), key=lambda pair: -pair[1])
        ],
        "rules": STATE.rules,
        "engine": {
            "built_at": STATE.promos["built_at"],
            "took_ms": STATE.promos["took_ms"],
            "triggers": len(STATE.promos["offers"]),
            "llm_written": STATE.promos.get("llm_written", 0),
            "llm_provider": llm.provider_name(),
            "llm_model": os.getenv("LLM_MODEL", ""),
        },
    }


@app.get("/admin/offers")
def admin_offers():
    """Ranked offers per trigger with the score breakdown, for the 'Offers & logic' tab."""
    names = STATE.catalog["name"].to_dict()
    return [
        {"trigger_sku": sku, "trigger_name": names.get(sku, sku), "offers": offers}
        for sku, offers in STATE.promos["offers"].items()
    ]


@app.put("/admin/rules", response_model=RebuildResponse)
def admin_rules(body: Rules):
    """Save store rules and re-price every offer. LLM picks are reused where the shortlist is unchanged."""
    with LOCK:
        save_rules(body.model_dump())
        STATE.reload_catalog()
        STATE.set_promos(recommend.rebuild())
    return {"offers": len(STATE.promos["offers"]), "took_ms": STATE.promos["took_ms"]}


@app.post("/admin/stock", response_model=StockResponse)
def admin_stock(body: StockUpdate):
    if body.sku not in STATE.catalog.index:
        raise HTTPException(404, f"Unknown product: {body.sku}")
    with LOCK:
        set_stock({body.sku: body.stock}, relative=False)
    return {"sku": body.sku, "stock": body.stock}
