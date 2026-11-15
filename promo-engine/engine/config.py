import csv
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

IST = timezone(timedelta(hours=5, minutes=30), "IST")

# Discount columns were added after the first dataset; older store_rules.csv files fall back to these.
RULE_DEFAULTS = {
    "expiry_discount_days": "3",
    "expiry_discount_pct": "30",
    "discount_tiers": "21:10|30:20|40:25",
}
RULE_COLUMNS = [
    "min_margin_pct", "max_discount_pct", "dead_stock_days", "near_expiry_days", "promo_valid_hours",
    "max_uses_per_code", "max_discounted_units", "expiry_discount_days", "expiry_discount_pct", "discount_tiers",
]


def data_dir() -> Path:
    return Path(os.getenv("PROMO_DATA_DIR", ROOT / "data"))


def cache_dir() -> Path:
    path = Path(os.getenv("PROMO_CACHE_DIR", ROOT / "cache"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_rules() -> dict:
    """Store rules as ints, plus discount_tiers as [{"days": 21, "pct": 10}, ...] (stored as "21:10|30:20")."""
    with (data_dir() / "store_rules.csv").open(newline="", encoding="utf-8") as f:
        row = {**RULE_DEFAULTS, **next(csv.DictReader(f))}
    tiers = [pair.split(":") for pair in row.pop("discount_tiers").split("|") if pair]
    rules = {key: int(value) for key, value in row.items()}
    rules["discount_tiers"] = sorted(({"days": int(d), "pct": int(p)} for d, p in tiers), key=lambda t: t["days"])
    return rules


def save_rules(rules: dict) -> None:
    row = {**rules, "discount_tiers": "|".join(f"{t['days']}:{t['pct']}" for t in rules["discount_tiers"])}
    header = ",".join(RULE_COLUMNS)
    values = ",".join(str(row[column]) for column in RULE_COLUMNS)
    write_atomic(data_dir() / "store_rules.csv", f"{header}\n{values}\n")


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
