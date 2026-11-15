# 🛒 Dead-Stock Promo Engine

> **A smart promo service for online grocery stores** that finds slow-moving inventory and pairs it with shopper carts using RAG + LLM, then prices it with margin-safe discounts in real time.

---

## ✨ What It Does

When a shopper adds **Green Tea** to their cart at checkout, the engine:

1. **Finds** Honey (slow-moving, 42 days unsold)
2. **Calculates** a margin-safe discount (25% off)
3. **Shows** a personalized pop-up: *"Add a touch of natural sweetness to your tea"*
4. **Applies** the promo code `DEAD25-HNY500`
5. **Signs** the total with a tamper-proof JWT
6. **Decrements** inventory.csv when paid

The **admin panel** lets you watch stock live, edit discount tiers, inspect the scoring logic, and see who bought what—all in real time.

---

## 🏗️ Architecture

### Offline Pipeline (Startup, `POST /admin/rebuild`)
```
data/*.csv ──> loader ──> Chroma index ──> recommend ──> LLM ──> pricing ──> promos.json
              (stuck     (embeddings)       (retrieve,    (pick  (tiers,     (cached
              score)     MiniLM model       filter,       one,   margin      ranked
                                           score)        write) floor,      offers)
                                                               code)
```

### Live Checkout (Cache lookups, no model calls)
```
widget.js ──> POST /recommend ──> pop-up ──> POST /cart/apply ──> Pay ──> POST /order/confirm
(getCart)    (cached offer +    (Add &     (server prices,        (JWT  (idempotent,
             cart guardrails)   apply)      returns signed JWT)    verify) stock decrement)
```

---

## 🚀 Quick Start

### Setup (Windows PowerShell)

**One-time only:**

```powershell
cd promo-engine
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # Set LLM_PROVIDER=none to run without a key

cd ..\grocergo
npm install
```

**`grocergo\.env.local` (auto-created by `start-demo.bat`):**

```
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<any random string>
```

### Run

**Quickest: double-click `HACKATHON\start-demo.bat`** (opens both terminals)

Or by hand:

```powershell
# Terminal 1
cd promo-engine
.venv\Scripts\activate
python scripts\generate_data.py
uvicorn api.main:app --reload --port 8000

# Terminal 2
cd grocergo
npm run dev
```

**Open:**

| What | Where |
|---|---|
| 🛍️ **Store** | http://localhost:3000 |
| 🧠 **Admin panel** | http://localhost:8000/admin |
| 📚 **API docs** | http://localhost:8000/docs |
| 🪟 **Widget alone** | http://localhost:8000/widget/test.html |

---

## 📊 2-Minute Demo

1. **Sign in** as Demo Shopper on http://localhost:3000
2. **Add Green Tea 100g** (Beverages)
3. **Go to checkout** → pop-up appears: *"Organic Honey 500g · ₹450 → ₹337.50 (25% off)"*
4. **Click Add & apply** → code `DEAD25-HNY500` applied, totals: ₹557.50
5. **Click Pay** → success screen shows stock left (Honey: 40 → 39)
6. **Open admin** http://localhost:8000/admin → see order in feed with customer email

**Guardrail test:** Add Green Tea + Sugar-Free Sweetener → Honey is **not** offered (diet conflict); Namkeen Mixture is offered instead.

---

## 🎛️ Admin Panel

Five tabs to manage everything:

### **Overview**
- KPIs: Orders, revenue, discount given, dead-stock count, cash tied up
- Latest orders feed with customer names
- Code redemption tracker

### **Live Stock**
- All 65 products with stock, days unsold, expiry, stuck score
- Current promo (if any) and discount %
- Search, filter by dead/low stock
- **Set stock** button per product (edits `inventory.csv` live)

### **Offers & Logic**
- The rules explained in plain words
- Pick any cart product to see its top 5 candidates
- Score breakdown: pairs-with match, bought-together lift, vector similarity, fit, stuck score, final score
- Whether the LLM picked it or the template was used

### **Orders**
- Real-time order feed: when, who, items, code, discount, amount
- Toast notification on each new order

### **Discount Settings**
- **Guardrails:** margin floor %, discount cap, dead-stock days, near-expiry days, code validity, max uses per code
- **Discount tiers:** "At 21 days unsold give 10% off" → editable, add/remove tiers
- **Near-expiry:** override tier discount for items expiring within N days
- Saving writes `store_rules.csv` and re-prices every offer in ~20 seconds

---

## 📁 Project Structure

```
HACKATHON/
├── promo-engine/              # The backend
│   ├── engine/
│   │   ├── loader.py          # Load products, merge inventory, compute stuck score
│   │   ├── index.py           # Chroma embeddings (MiniLM, persistent cache)
│   │   ├── copurchase.py      # Pair lift from orders.csv
│   │   ├── recommend.py       # Retrieve, filter, score, ask LLM, apply guardrails
│   │   ├── llm.py             # Provider-agnostic (anthropic/openai/groq/none)
│   │   ├── pricing.py         # Discount tiers, margin floor, cart totals
│   │   ├── signing.py         # HS256 JWT (code, total, cart hash, order ref)
│   │   └── config.py          # Settings loader (store_rules.csv), atomic writes
│   ├── api/
│   │   └── main.py            # FastAPI app (30 endpoints + /admin HTML)
│   ├── admin/
│   │   └── index.html         # Admin panel (single-page, no build step)
│   ├── widget/
│   │   ├── widget.js          # Plain JS widget (no build, framework-agnostic)
│   │   ├── widget.css         # Styled pop-up, code input, summary
│   │   └── test.html          # Standalone test page
│   ├── tests/
│   │   ├── conftest.py        # Fixtures (fresh dataset, client)
│   │   ├── test_api.py        # 16 tests for the API (pricing, guardrails, tamper-proofing)
│   │   └── test_admin.py      # 14 tests for the admin panel (rules, stock, offers)
│   ├── scripts/
│   │   ├── generate_data.py   # Generate 65 products, CSVs, Chroma index
│   │   └── export_store_products.py  # Export products.json for the store
│   ├── data/
│   │   ├── products.csv       # SKU, name, category, price, cost, description, etc.
│   │   ├── inventory.csv      # Stock levels (decremented on /order/confirm)
│   │   ├── orders.csv         # 1868 past orders (for co-purchase analysis)
│   │   └── store_rules.csv    # Discount tiers, margin floor, thresholds (editable)
│   ├── cache/
│   │   ├── chroma/            # Persistent embeddings
│   │   ├── promos.json        # Cached offers (rebuilt on startup or admin/rebuild)
│   │   ├── llm_picks.json     # LLM choices (reused while shortlist unchanged)
│   │   ├── usage.json         # Code redemption counters
│   │   └── orders_log.csv     # Complete order history (append-only)
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
│
├── grocergo/                  # The Next.js store
│   ├── src/
│   │   ├── app/
│   │   │   ├── checkout/page.jsx       # NEW: Widget integration
│   │   │   └── auth/[...nextauth]/     # NEW: Demo shopper provider
│   │   ├── components/
│   │   │   ├── shared/Catalog.js       # CHANGED: Use promo products
│   │   │   ├── navbar/Login/           # CHANGED: Demo shopper button
│   │   │   └── navbar/Cart/            # CHANGED: CHECKOUT → /checkout link
│   │   └── data/
│   │       └── promo-products.json     # NEW: Generated by export_store_products.py
│   ├── package.json
│   ├── .env.local             # Generated by start-demo.bat
│   └── [... rest of Next.js app]
│
├── start-demo.bat             # Batch script to launch both terminals
└── README.md                  # This file
```

---

## 🔑 Key Concepts

### **Stuck Score** (0–1 scale)
Identifies which products are dead stock:
```
stuck = 0.5 × min(days_unsold/60, 1)
      + 0.3 × min(stock/100, 1)
      + 0.2 × expiry_urgency
```

Higher score = slower mover = better promo candidate.

### **Discount Tiers**
Automatic based on days unsold:
- **21+ days:** 10% off
- **30+ days:** 20% off
- **40+ days:** 25% off
- **Expires within 3 days:** 30% instead
- **Capped at 30%**

### **Margin Floor**
Prevents overselling. New price must be ≥ cost × (1 + min_margin_pct/100).

Example: Honey costs ₹300, margin floor is 10% → new price must be ≥ ₹330. A 25% discount gives ₹337.50 ✓

Milk costs ₹50, margin floor is 10% → new price must be ≥ ₹55. At 30% expiry discount, that's ₹42, which fails. Discount is lowered to 8% → ₹55.20 ✓

### **Tamper-Proof Totals**
Every `/cart/apply` returns a JWT signed with:
- `code` (if any)
- `final_total`
- `cart_hash` (SHA-256 of sorted items)
- `order_ref` (uuid4, for idempotency)
- `exp` (15 minutes)

At `/order/confirm`, the JWT is verified and cart hash is recalculated. If the cart was modified, the order is rejected.

### **Diet Guardrails**
Products have an `avoid_with` column. If a cart contains "Sugar-Free Sweetener", the engine won't suggest Honey (marked `avoid_with: sugar-free`). Instead, the next-best candidate is offered.

### **LLM Provider Agnostic**
Supports:
- **Anthropic** (Claude): `claude-sonnet-5-5`
- **OpenAI** (GPT-4o): `gpt-4o-mini`
- **Groq** (open/gpt-oss-120b): free tier, 8k TPM
- **None** (template fallback): "Pairs with your Green Tea"

Set `LLM_PROVIDER` in `.env` and provide the matching API key. The message never contains prices—widget shows those.

---

## 🧪 Tests

30 tests, all passing:

```powershell
cd promo-engine
.venv\Scripts\activate
pytest
```

| File | Tests | What |
|---|---|---|
| `test_api.py` | 16 | Green tea → honey offer, guardrails, tamper-proofing, code logic |
| `test_admin.py` | 14 | Admin data, rules editing, stock updates, offer scoring |

---

## 🛠️ Technical Stack

| Layer | Stack |
|---|---|
| **Backend** | FastAPI, Uvicorn |
| **Frontend (Store)** | Next.js 14, Tailwind, NextAuth (custom provider) |
| **Widget** | Plain JavaScript (no build, framework-agnostic) |
| **Admin Panel** | Vanilla JS + HTML + CSS (no build) |
| **Database** | CSV files + SQLite (Chroma) for embeddings |
| **ML** | Sentence Transformers (MiniLM-L6-v2) |
| **Tests** | pytest + FastAPI TestClient |

---

## 📈 Live Metrics

The admin panel shows:

- **Orders placed** with customer emails
- **Revenue** after discounts
- **Dead-stock count** and value at cost
- **Offer performance** (how many times each code was used)
- **LLM vs. template breakdown** (how many offers got custom copy)
- **Offers rebuilt** time and trigger count

---

## 🚫 Known Limitations

- **CSV instead of a database** → one process-wide lock around writes
- **Single store, single rules row**
- **Mock payment** → "Pay" only confirms the order and decrements stock
- **No auth on the API or admin panel** → fine for localhost, not beyond
- **Store sections we don't cover** (offers, frozen, petshop) still show template products with no SKU
- **LLM with `LLM_PROVIDER=none`** → uses template message and top-scored candidate
- **No honey image** → reuses maple syrup picture from template
- **Offer copy never has prices** → widget shows those from server data

---

## 🎯 How to Extend

### Add a new product
Edit `promo-engine\data\products.csv` or `scripts\generate_data.py`, then:
```powershell
python scripts\generate_data.py
python scripts\export_store_products.py
```

### Change discount rules
Open admin panel → **Discount settings** → edit and save. Or edit `store_rules.csv` directly.

### Use a real LLM
Set in `.env`:
```
LLM_PROVIDER=groq
API_KEY=gsk_...
```
Then press **Rebuild** on the admin panel.

### Change the widget style
Edit `promo-engine\widget\widget.css` (no build step needed).

### Add a new endpoint
Add to `promo-engine\api\main.py`. OpenAPI docs auto-generate at `/docs`.

---

## 📝 License

Hackathon demo. No license. Use freely.

---

## 👤 Author

**Mohammed Mohsin** — [GitHub](https://github.com/mohammedmohsin203)  
Email: mohammedmohsin203@gmail.com

Built for a hackathon. The goal was to show **reliable end-to-end demo over polish**. Every decision prioritized that: plain CSV, single lock, template fallback, no auth, all tests running in 30 seconds.

---

## 🔗 Links

- **Admin:** http://localhost:8000/admin
- **API docs:** http://localhost:8000/docs
- **Widget test:** http://localhost:8000/widget/test.html
- **Store:** http://localhost:3000

---

> **Ready to ship.** All 30 tests passing. Demo runs on any Windows laptop with no API key. Checkout is tamper-proof. Rules are live-editable. Stock is real-time.
