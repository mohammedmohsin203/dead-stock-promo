"""Export the promo-engine catalog to the GrocerGo store so both sides share SKUs.

Usage: python scripts\\export_store_products.py
Writes grocergo\\src\\data\\promo-products.json (read by src\\components\\shared\\Catalog.js).
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT.parent / "grocergo" / "src" / "data" / "promo-products.json"

# Our category -> an existing GrocerGo section route (src\app\sections\<section>)
SECTIONS = {
    "Beverages": "beverages",
    "Pantry": "essentials",
    "Dairy": "cheeses-and-dairy",
    "Produce": "fruits",
    "Snacks": "snacks",
    "Bakery": "bakery",
    "Breakfast": "full-fridge",
    "Personal Care": "cleaning",
}


def url_words(name: str) -> str:
    """Mirror of the store's UrlizeWords.js, as the product page looks the URL up in search_words."""
    slug = re.sub(r"\s+", "-", name.lower())
    slug = re.sub(r"(?<![a-zA-Z])[0-9%]+", "", slug)
    slug = re.sub(r"-+", "-", slug).replace("&", "and", 1).removeprefix("-")
    return re.sub(r" +", " ", slug.replace("-", " "))


def read(name: str) -> list[dict]:
    with (ROOT / "data" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    prices = {row["sku"]: float(row["price"]) for row in read("inventory.csv")}
    products = []
    for number, p in enumerate(read("products.csv"), start=1):
        words = [url_words(p["name"]), p["name"].lower(), *p["tags"].split("|")]
        products.append({
            "id": number,
            "sku": p["sku"],
            "name": p["name"],
            "price": prices[p["sku"]],
            "old_price": 0,
            "image": p["image"],
            "category": p["category"],
            "section": SECTIONS[p["category"]],
            "search_words": list(dict.fromkeys(w for w in words if w)),
        })
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(products)} products to {TARGET}")


if __name__ == "__main__":
    main()
