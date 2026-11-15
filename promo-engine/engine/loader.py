import re
from datetime import date

import pandas as pd

from .config import data_dir

TEXT_COLUMNS = ["name", "category", "description", "tags", "pairs_with", "avoid_with", "image"]


def load_catalog(rules: dict, today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    products = pd.read_csv(data_dir() / "products.csv", dtype=str).fillna("")
    inventory = pd.read_csv(data_dir() / "inventory.csv", dtype={"sku": str})
    df = products.merge(inventory, on="sku", how="inner")
    df[TEXT_COLUMNS] = df[TEXT_COLUMNS].fillna("")
    df["days_to_expiry"] = [(date.fromisoformat(d) - today).days for d in df["expiry_date"]]

    near = rules["near_expiry_days"]
    # expiry_urgency: 1 when days_to_expiry <= near_expiry_days, falling linearly to 0 at 30 days.
    urgency = ((30 - df["days_to_expiry"]) / (30 - near)).clip(0, 1)
    # stuck (0-1) = 0.5*min(days_unsold/60, 1) + 0.3*min(stock/100, 1) + 0.2*expiry_urgency
    df["stuck"] = (
        0.5 * (df["days_unsold"] / 60).clip(upper=1)
        + 0.3 * (df["stock"] / 100).clip(upper=1)
        + 0.2 * urgency
    ).round(4)
    df["is_dead"] = (
        (df["days_unsold"] >= rules["dead_stock_days"]) | (df["days_to_expiry"] <= near)
    ) & (df["stock"] > 0)
    return df.set_index("sku", drop=False)


def keywords(pipe_separated: str) -> list[str]:
    return [k.strip().lower() for k in pipe_separated.split("|") if k.strip()]


def mentions(pipe_separated: str, product) -> bool:
    """True if any keyword appears (at a word start) in the product's name or tags."""
    text = f"{product['name']} {product['tags'].replace('|', ' ')}".lower()
    return any(re.search(rf"\b{re.escape(k)}", text) for k in keywords(pipe_separated))
