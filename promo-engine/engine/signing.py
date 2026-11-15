import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt

TOKEN_MINUTES = 15


def _secret() -> str:
    secret = os.getenv("SIGNING_SECRET")
    if not secret:
        raise RuntimeError("SIGNING_SECRET is not set (copy .env.example to .env)")
    return secret


def cart_hash(items: dict[str, int]) -> str:
    canonical = ",".join(f"{sku}:{qty}" for sku, qty in sorted(items.items()))
    return hashlib.sha256(canonical.encode()).hexdigest()


def sign_totals(code: str | None, final_total: float, discount: float, items: dict[str, int]) -> str:
    payload = {
        "code": code,
        "final_total": f"{final_total:.2f}",
        "discount": f"{discount:.2f}",
        "cart_hash": cart_hash(items),
        "order_ref": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_totals(token: str) -> dict:
    """Raises jwt.InvalidTokenError on a bad signature or an expired token."""
    return jwt.decode(token, _secret(), algorithms=["HS256"])
