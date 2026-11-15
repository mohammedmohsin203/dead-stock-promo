"""Generate the demo dataset (products, inventory, orders, store rules) with a fixed seed.

Usage: python scripts\\generate_data.py [output_dir]
Dates are relative to the day the script runs.
"""
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
IMG = "/images/products/"

# sku, name, category, price, description, tags, pairs_with, avoid_with, image
PRODUCTS = [
    # Beverages
    ("GT100", "Green Tea 100g", "Beverages", 220, "Light whole-leaf green tea from the Nilgiris.", "green tea|tea|healthy|antioxidant", "honey|lemon|biscuits", "", "beverages/mint-tea.webp"),
    ("TULSI", "Tulsi Green Tea 100g", "Beverages", 240, "Green tea blended with holy basil.", "green tea|tea|tulsi|herbal", "honey|lemon", "", "dietary/detox.webp"),
    ("MNG1L", "Mango Juice 1L", "Beverages", 120, "Alphonso mango fruit drink.", "juice|mango|fruit drink", "snacks|chips", "", "beverages/mango-juice.webp"),
    ("BT250", "Assam Black Tea 250g", "Beverages", 180, "Strong CTC black tea for daily chai.", "black tea|tea|chai", "biscuits|milk|sugar", "", "beverages/black-teas.webp"),
    ("COF200", "Filter Coffee 200g", "Beverages", 260, "South Indian filter coffee with chicory.", "coffee|filter coffee", "milk|sugar|biscuits", "", "essentials/coffee-beans.webp"),
    ("OJ1L", "Orange Juice 1L", "Beverages", 140, "No-added-sugar orange juice.", "juice|orange|breakfast", "bread|eggs", "", "beverages/orange-juice.webp"),
    ("CW500", "Tender Coconut Water 500ml", "Beverages", 70, "Natural tender coconut water.", "coconut water|hydration", "fruit", "", "beverages/coconut-water.webp"),
    ("COLA", "Cola Soft Drink 750ml", "Beverages", 45, "Chilled fizzy cola.", "soft drink|cola|fizzy", "chips|popcorn|snacks", "", "snacks/soft-drink.webp"),
    ("NIMB", "Nimbu Soda 300ml", "Beverages", 30, "Sparkling lemon soda.", "soft drink|lemon soda", "chips|namkeen", "", "beverages/green-lemon-juice.webp"),
    ("WTR1L", "Mineral Water 1L", "Beverages", 20, "Packaged drinking water.", "water|hydration", "lemon", "", "essentials/water.webp"),
    # Pantry
    ("HNY500", "Organic Honey 500g", "Pantry", 450, "Raw organic forest honey.", "honey|natural sweetener|organic", "green tea|oats|bread|lemon", "sugar-free|diabetic", "offers/maple-syrup.webp"),
    ("SF100", "Sugar-Free Sweetener", "Pantry", 180, "Zero-calorie sweetener tablets for diabetic diets.", "sugar-free|sweetener|diabetic|diet", "green tea|coffee", "", "essentials/sugar2.webp"),
    ("RICE5", "Basmati Rice 5kg", "Pantry", 650, "Aged long-grain basmati rice.", "rice|basmati|staple", "dal|ghee", "", "essentials/rice.webp"),
    ("ATTA5", "Whole Wheat Atta 5kg", "Pantry", 280, "Stone-ground chakki atta.", "atta|flour|staple", "ghee|dal", "", "essentials/flour2.webp"),
    ("SUG1", "Sugar 1kg", "Pantry", 50, "Refined white sugar.", "sugar|sweet|staple", "tea|coffee", "", "essentials/sugar2.webp"),
    ("SALT1", "Iodised Salt 1kg", "Pantry", 28, "Free-flow iodised salt.", "salt|staple", "", "", "essentials/salt2.webp"),
    ("OIL1", "Sunflower Oil 1L", "Pantry", 160, "Refined sunflower cooking oil.", "oil|cooking", "atta|rice", "", "essentials/oil.webp"),
    ("OLV500", "Extra Virgin Olive Oil 500ml", "Pantry", 599, "Cold-pressed olive oil.", "olive oil|oil|italian", "pasta|bread|salad", "", "essentials/olive-oil.webp"),
    ("PASTA", "Penne Pasta 500g", "Pantry", 110, "Durum wheat penne.", "pasta|penne|italian", "pasta sauce|cheese|olive oil", "", "offers/macaroni.webp"),
    ("PSAUCE", "Pasta Sauce 400g", "Pantry", 150, "Tomato basil pasta sauce.", "pasta sauce|sauce|tomato|italian", "pasta|cheese", "", "canneds/tomato-sauce.webp"),
    ("DAL1", "Toor Dal 1kg", "Pantry", 170, "Unpolished toor dal.", "dal|lentils|staple", "rice|ghee", "", "essentials/bean.webp"),
    ("TURM", "Turmeric Powder 200g", "Pantry", 60, "Ground haldi.", "turmeric|spice|masala", "dal|milk", "", "seasoning/turmeric.webp"),
    ("JAM", "Mixed Fruit Jam 500g", "Pantry", 165, "Classic mixed fruit jam.", "jam|spread|sweet", "bread|butter", "sugar-free|diabetic", "full-fridge/salsa.webp"),
    ("PICKLE", "Mango Pickle 400g", "Pantry", 130, "Spicy Andhra-style mango pickle.", "pickle|achar|spicy", "rice|dal|curd", "", "canneds/peach.webp"),
    ("RAJMA", "Canned Rajma 400g", "Pantry", 95, "Ready-to-cook red kidney beans.", "rajma|beans|canned", "rice", "", "canneds/beans.webp"),
    # Dairy
    ("MLK1L", "Toned Milk 1L", "Dairy", 60, "Fresh pasteurised toned milk.", "milk|dairy|fresh", "cereal|oats|tea", "", "full-fridge/milk.webp"),
    ("BTR100", "Salted Butter 100g", "Dairy", 58, "Creamy table butter.", "butter|dairy|spread", "bread|pav", "", "cheeses-and-dairy/cream-cheese.webp"),
    ("PNR200", "Fresh Paneer 200g", "Dairy", 95, "Soft malai paneer.", "paneer|dairy|protein", "bell pepper|atta", "", "cheeses-and-dairy/mozzarella.webp"),
    ("CURD400", "Curd 400g", "Dairy", 40, "Thick set dahi.", "curd|dahi|dairy", "rice|pickle", "", "frozen/yogurt.webp"),
    ("CHS", "Cheese Slices 200g", "Dairy", 135, "Processed cheese slices.", "cheese|dairy|sandwich", "bread|pasta", "", "cheeses-and-dairy/cheese-slice.webp"),
    ("GHEE500", "Cow Ghee 500ml", "Dairy", 340, "Pure cow ghee.", "ghee|dairy|cooking", "rice|dal|atta", "", "cheeses-and-dairy/gouda.webp"),
    ("LASSI", "Mango Lassi 200ml", "Dairy", 35, "Chilled mango lassi.", "lassi|dairy|drink|mango", "snacks|namkeen", "", "frozen/peach-yogurt.webp"),
    # Produce
    ("LEM6", "Lemons (6 pcs)", "Produce", 60, "Juicy fresh lemons.", "lemon|citrus|fresh", "green tea|water", "", "fruits/lemons.webp"),
    ("APL1", "Shimla Apples 1kg", "Produce", 180, "Crisp red apples.", "apple|fruit|fresh", "oats|muesli", "", "fruits/apples.webp"),
    ("AVO2", "Avocados (2 pcs)", "Produce", 199, "Ripe Hass avocados.", "avocado|fruit|fresh", "bread|lemon", "", "fruits/avocados.webp"),
    ("PINE", "Pineapple (1 pc)", "Produce", 90, "Sweet whole pineapple.", "pineapple|fruit|fresh", "curd", "", "fruits/pineapple.webp"),
    ("STRW", "Strawberries 200g", "Produce", 120, "Mahabaleshwar strawberries.", "strawberry|fruit|fresh", "muesli|oats|curd", "", "fruits/strawberry.webp"),
    ("WMEL", "Watermelon (1 pc)", "Produce", 80, "Seedless watermelon.", "watermelon|fruit|fresh", "", "", "fruits/watermelon.webp"),
    ("BPEP", "Bell Peppers 500g", "Produce", 75, "Mixed capsicum.", "bell pepper|capsicum|vegetable", "paneer|pasta", "", "rotisserie/bell-pepper.webp"),
    # Snacks
    ("OATC", "Oats Cookies Pack", "Snacks", 99, "Crunchy oats and jaggery cookies.", "cookies|biscuits|oats", "tea|coffee|milk", "", "snacks/cookie.webp"),
    ("CHIPS", "Masala Potato Chips 150g", "Snacks", 50, "Spicy masala potato chips.", "chips|snacks|salty", "soft drink|cola|juice", "", "snacks/chips.webp"),
    ("POPC", "Butter Popcorn 100g", "Snacks", 60, "Ready-to-eat butter popcorn.", "popcorn|snacks", "soft drink|cola", "", "snacks/popcorn.webp"),
    ("CHOC", "Dark Chocolate Bar 80g", "Snacks", 110, "55% cocoa dark chocolate.", "chocolate|sweet|snacks", "coffee|milk", "", "snacks/chocolate-bar.webp"),
    ("MARIE", "Marie Biscuits 250g", "Snacks", 35, "Light tea-time biscuits.", "biscuits|tea-time|snacks", "tea|coffee", "", "sweets/cookie.webp"),
    ("NAMK", "Namkeen Mixture 400g", "Snacks", 120, "Spicy sev and peanut mixture.", "namkeen|snacks|salty", "tea|soft drink|lassi", "", "frozen/french-fries.webp"),
    ("SANDW", "Veg Sandwich", "Snacks", 70, "Fresh grilled veg sandwich.", "sandwich|snacks|ready to eat", "juice|coffee", "", "snacks/sandwich.webp"),
    # Bakery
    ("BREAD", "Whole Wheat Bread 400g", "Bakery", 45, "Soft whole wheat sandwich bread.", "bread|bakery|breakfast", "butter|jam|eggs|honey", "", "full-fridge/garlic-bread.webp"),
    ("GBRD", "Garlic Bread", "Bakery", 90, "Buttery garlic bread loaf.", "garlic bread|bakery", "pasta|cheese", "", "full-fridge/garlic-bread.webp"),
    ("CINN", "Cinnamon Rolls (4 pcs)", "Bakery", 160, "Soft glazed cinnamon rolls.", "cinnamon roll|bakery|sweet", "coffee|milk", "", "full-fridge/cinnamon-roll.webp"),
    ("DONUT", "Chocolate Donuts (4 pcs)", "Bakery", 140, "Chocolate glazed donuts.", "donut|bakery|sweet", "coffee|milk", "", "sweets/donut.webp"),
    ("PAV", "Pav Buns (6 pcs)", "Bakery", 35, "Soft ladi pav.", "pav|buns|bakery", "butter", "", "full-fridge/garlic-bread.webp"),
    ("RUSK", "Elaichi Cake Rusk 300g", "Bakery", 85, "Crisp cardamom cake rusk.", "rusk|biscuits|bakery|tea-time", "tea|coffee|chai", "", "sweets/cookie.webp"),
    # Breakfast
    ("OATS1", "Rolled Oats 1kg", "Breakfast", 190, "Wholegrain rolled oats.", "oats|cereal|breakfast|healthy", "milk|honey|fruit", "", "dietary/protein.webp"),
    ("CFLK", "Corn Flakes 500g", "Breakfast", 175, "Crunchy corn flakes.", "cereal|corn flakes|breakfast", "milk|honey", "", "dietary/vitamin-b.webp"),
    ("MUESLI", "Fruit & Nut Muesli 750g", "Breakfast", 399, "Muesli with almonds and raisins.", "muesli|cereal|breakfast", "milk|curd|oats", "", "dietary/vitamin-d.webp"),
    ("EGGS12", "Farm Eggs (12 pcs)", "Breakfast", 96, "Fresh white eggs.", "eggs|protein|breakfast", "bread|butter", "", "eggs/eggs.webp"),
    ("MSYR", "Maple Syrup 250ml", "Breakfast", 520, "Pure Canadian maple syrup.", "maple syrup|syrup|sweet", "oats|bread|cereal", "sugar-free|diabetic", "offers/maple-syrup.webp"),
    ("PBTR", "Crunchy Peanut Butter 340g", "Breakfast", 210, "Roasted crunchy peanut butter.", "peanut butter|spread|protein", "bread|oats", "", "cheeses-and-dairy/cream-cheese.webp"),
    ("POHA", "Thick Poha 500g", "Breakfast", 55, "Flattened rice for poha.", "poha|breakfast|staple", "lemon|namkeen", "", "essentials/rice.webp"),
    # Personal Care
    ("SOAP", "Neem Bath Soap (3 pack)", "Personal Care", 105, "Neem and tulsi bathing bar.", "soap|bath|neem", "handwash", "", "cleaning/soap.webp"),
    ("HWASH", "Antiseptic Handwash 250ml", "Personal Care", 99, "Germ-protection liquid handwash.", "handwash|antiseptic|hygiene", "soap|paper towels", "", "cleaning/antiseptic.webp"),
    ("PTWL", "Paper Towels (2 rolls)", "Personal Care", 120, "Absorbent kitchen towels.", "paper towels|tissue|hygiene", "handwash", "", "essentials/paper-towel.webp"),
    ("VITC", "Vitamin C Tablets (60)", "Personal Care", 299, "Chewable vitamin C with zinc.", "vitamin c|supplement|immunity", "orange|juice|lemon", "", "dietary/vitamin-c.webp"),
    ("TPICK", "Bamboo Toothpicks (200)", "Personal Care", 40, "Eco-friendly bamboo toothpicks.", "toothpicks|hygiene", "", "", "essentials/toothpick.webp"),
    ("SPNG", "Bath Sponge", "Personal Care", 65, "Soft exfoliating bath sponge.", "sponge|bath", "soap", "", "cleaning/sponge.webp"),
]

# sku: (cost, stock, days_unsold, expiry_offset_days) -- exact values the demo depends on
FIXED = {
    "GT100": (150, 50, 3, 200),
    "HNY500": (300, 40, 42, 35),
    "SF100": (120, 30, 12, 100),
    "LEM6": (40, 25, 2, 4),
    "OATC": (60, 70, 31, 20),
    "MNG1L": (80, 60, 28, 10),
    "TULSI": (160, 35, 25, 180),
    "MLK1L": (50, 20, 0, 2),
}

# sku: (days_unsold, expiry_offset_days) for the remaining clearly-dead products
DEAD = {
    "PICKLE": (48, 150),
    "JAM": (33, 90),
    "OLV500": (55, 240),
    "MUESLI": (36, 60),
    "MSYR": (44, 300),
    "PBTR": (27, 120),
    "RUSK": (23, 25),
    "NAMK": (30, 18),
    "VITC": (52, 200),
    "LASSI": (5, 3),
    "DONUT": (4, 2),
}

# (sku_a, sku_b, weight) pairings planted into orders so co-purchase has signal
PAIRINGS = [
    ("GT100", "HNY500", 9),
    ("GT100", "LEM6", 6),
    ("BREAD", "BTR100", 9),
    ("OATS1", "MLK1L", 8),
    ("CHIPS", "COLA", 8),
    ("PASTA", "PSAUCE", 8),
    ("BT250", "MARIE", 7),
    ("RICE5", "DAL1", 5),
    ("BREAD", "EGGS12", 4),
]


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def generate(out_dir: Path) -> None:
    rng = random.Random(SEED)
    today = date.today()
    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        out_dir / "products.csv",
        ["sku", "name", "category", "description", "tags", "pairs_with", "avoid_with", "image"],
        [[sku, name, cat, desc, tags, pairs, avoid, IMG + image]
         for sku, name, cat, _price, desc, tags, pairs, avoid, image in PRODUCTS],
    )

    inventory = []
    for sku, _name, _cat, price, *_ in PRODUCTS:
        if sku in FIXED:
            cost, stock, days_unsold, expiry = FIXED[sku]
        elif sku in DEAD:
            days_unsold, expiry = DEAD[sku]
            cost = round(price * rng.uniform(0.55, 0.80))
            stock = rng.randint(60, 150)
        else:
            cost = round(price * rng.uniform(0.55, 0.80))
            stock = rng.randint(20, 120)
            days_unsold = rng.randint(0, 7)
            expiry = rng.randint(15, 300)
        inventory.append([sku, price, cost, stock, days_unsold, (today + timedelta(days=expiry)).isoformat()])
    write_csv(out_dir / "inventory.csv", ["sku", "price", "cost", "stock", "days_unsold", "expiry_date"], inventory)

    slow = set(DEAD) | {s for s, v in FIXED.items() if v[2] >= 21}
    skus = [p[0] for p in PRODUCTS]
    weights = [0.15 if s in slow else 1.0 for s in skus]
    orders = []
    for n in range(1, 501):
        basket = set()
        if rng.random() < 0.6:
            a, b, _ = rng.choices(PAIRINGS, weights=[w for *_, w in PAIRINGS])[0]
            basket.update((a, b))
        size = rng.randint(1, 6)
        while len(basket) < size:
            basket.add(rng.choices(skus, weights=weights)[0])
        for sku in sorted(basket):
            orders.append([f"ORD{n:04d}", sku, rng.randint(1, 3)])
    write_csv(out_dir / "orders.csv", ["order_id", "sku", "qty"], orders)

    write_csv(
        out_dir / "store_rules.csv",
        ["min_margin_pct", "max_discount_pct", "dead_stock_days", "near_expiry_days",
         "promo_valid_hours", "max_uses_per_code", "max_discounted_units",
         "expiry_discount_days", "expiry_discount_pct", "discount_tiers"],
        [[10, 30, 21, 10, 48, 50, 2, 3, 30, "21:10|30:20|40:25"]],
    )

    names = {p[0]: p[1] for p in PRODUCTS}
    dead_rows = [r for r in inventory
                 if r[4] >= 21 or (date.fromisoformat(r[5]) - today).days <= 10]
    print(f"Wrote dataset to {out_dir}")
    print(f"Products: {len(PRODUCTS)} | order lines: {len(orders)} | dead-stock: {len(dead_rows)}")
    print("\nDead stock (days unsold >= 21 or expiry within 10 days):")
    for sku, price, cost, stock, days_unsold, expiry in dead_rows:
        print(f"  {sku:7} {names[sku]:30} price {price:>4} cost {cost:>4} stock {stock:>4} unsold {days_unsold:>3}d  expires {expiry}")
    print("\nDemo rows:")
    for sku, price, cost, stock, days_unsold, expiry in inventory:
        if sku in FIXED:
            print(f"  {sku:7} {names[sku]:30} price {price:>4} cost {cost:>4} stock {stock:>4} unsold {days_unsold:>3}d  expires {expiry}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
    generate(target)
    if target == ROOT / "data":
        # Offers were priced against the old data; drop them so the API rebuilds on next start.
        for stale in ("promos.json", "usage.json"):
            (ROOT / "cache" / stale).unlink(missing_ok=True)
