# Promo Engine

A third-party "dead-stock promo" service for online grocery stores. It reads a store's inventory, finds slow-moving
stock, picks the best related slow item for whatever is in the shopper's cart (RAG + LLM), prices it with a
margin-safe discount, and shows it as a pop-up at checkout with a tamper-proof total.

Hackathon demo, not production. Runs fully on a Windows laptop with no API key.

## Architecture

```
OFFLINE (startup, POST /admin/rebuild)                      LLM is only ever called here

 data\*.csv ──> loader ──────> index (Chroma) ──> recommend ─────────────> llm ────────> pricing ──> cache\promos.json
 products       pandas merge   MiniLM embeddings  retrieve top 20 +        picks 1 of    tiers +     ranked offers
 inventory      stuck score    cache\chroma       pairs_with + co-purchase top 5, writes margin      per trigger SKU
 orders         is_dead                           filter, score            copy          floor,
 store_rules                                                               (guardrailed) code

LIVE (checkout)                                             cache lookups only, no model calls

 widget.js ──> POST /recommend ──> pop-up ──> POST /cart/apply ──────────> Pay ──> POST /order/confirm
 getCart()     cached offer +      Add &      server prices the cart,              verifies JWT + cart hash,
               cart guardrails     apply      returns totals + signed JWT          decrements inventory.csv
```

- `engine\loader.py` merges products + inventory and computes the stuck score.
- `engine\index.py` embeds products into a persistent Chroma collection.
- `engine\copurchase.py` computes pair lift from `orders.csv`.
- `engine\recommend.py` retrieves, filters, scores, asks the LLM, and applies request-time cart guardrails.
- `engine\llm.py` is provider-agnostic (`anthropic | openai | none`) with a deterministic fallback.
- `engine\pricing.py` owns every price: discount tiers, margin floor, code, cart totals.
- `engine\signing.py` signs totals as a 15-minute HS256 JWT bound to the cart contents.
- `api\main.py` is the FastAPI app; it also serves `widget\` and the `/admin` page.

## Setup (Windows, PowerShell)

One-time:

```powershell
cd promo-engine
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # then set LLM_PROVIDER=none to run without a key

cd ..\grocergo
npm install
```

`grocergo\.env.local` must exist for the demo login (it is git-ignored; `start-demo.bat` creates it if missing):

```
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<any random string>
```

## Run

Quickest: double-click `HACKATHON\start-demo.bat` (opens both terminals). Or by hand:

```powershell
# Terminal 1
cd promo-engine; .venv\Scripts\activate; python scripts\generate_data.py; uvicorn api.main:app --reload --port 8000

# Terminal 2
cd grocergo; npm run dev
```

Open:

- Store: http://localhost:3000
- Admin ("the brain"): http://localhost:8000/admin
- API docs: http://localhost:8000/docs
- Widget on a plain page: http://localhost:8000/widget/test.html

Notes:

- `generate_data.py` resets stock and dates and clears cached offers, so run it before each demo.
- The first start downloads the embedding model (~90 MB) and can take about a minute; later starts take a few seconds.
- If you change product names or prices in the generator, run `python scripts\export_store_products.py` to resync the store.
- To use a real LLM, set `LLM_PROVIDER` and the matching key in `.env`, restart, and press Rebuild on `/admin`.

Tests:

```powershell
cd promo-engine; .venv\Scripts\activate; pytest
```

## Admin panel

http://localhost:8000/admin (page in `admin\index.html`, refreshes every 3 seconds, no login).

| Tab | What it shows |
|---|---|
| Overview | Orders, revenue, discount given, dead-stock count, cash tied up, latest orders, code redemptions |
| Live stock | Every product with stock, days unsold, expiry, stuck score and current promo. Rows flash when stock changes. "Set stock" edits `inventory.csv` |
| Offers & logic | The rules in plain words, and for any cart product the top 5 candidates with their score breakdown (pairs-with, bought together, similarity, fit, stuck, final), discount and whether the LLM picked it |
| Orders | Live order feed: time, order id, customer, items, code, discount, paid. A toast appears on each new order |
| Discount settings | Edit margin floor, discount cap, dead-stock thresholds, code limits, discount tiers and the near-expiry discount. Saving writes `store_rules.csv` and re-prices every offer |

Admin endpoints: `GET /admin/data`, `GET /admin/offers`, `PUT /admin/rules`, `POST /admin/stock`, `POST /admin/rebuild`.

The customer shown on an order is whatever the store passes as `getCustomer()` in `PromoWidget.init` (GrocerGo passes the
signed-in email). LLM picks are cached in `cache\llm_picks.json` and reused while a product's shortlist is unchanged, so
re-pricing after a settings change does not spend the LLM rate limit again.

## 2-minute demo script

0. On http://localhost:3000 click the cart icon and choose **Demo shopper** (one-time sign-in).
1. Go to **All sections → Beverages**, add **Green Tea 100g**, open the cart and click **CHECKOUT**.
2. The pop-up appears: "Pairs with your Green Tea · Organic Honey 500g ₹450 → ₹337.50 (25% off) · Add & apply",
   with the reason "42 days unsold, 40 in stock".
3. Click **Add & apply**. Honey is added, `DEAD25-HNY500` is applied, and the totals update from the server
   (₹670.00 − ₹112.50 = ₹557.50).
4. Click **Pay ₹557.50**. "Paid ₹557.50 · Order GG-…" appears with "Stock left: … Organic Honey 500g 39",
   and `data\inventory.csv` shows honey at 39.
5. Guardrail: add **Green Tea** and **Sugar-Free Sweetener** (Essentials section) and go to checkout.
   Honey is not offered (diet conflict); Namkeen Mixture is offered instead.

Show http://localhost:8000/admin alongside: the dead-stock list with stuck scores, and each trigger → target offer.
Tulsi Green Tea is in the dead-stock list but is never offered for a green tea cart (same-category substitute).

## Store integration notes

Findings from exploring `grocergo` (github.com/lucasdota/grocergo) before changing it.

- **Framework:** Next.js 14.0.3, App Router, code in `src\app` (shared components in `src\components`). Tailwind 3.
- **Product data:** hardcoded arrays in `src\components\shared\Catalog.js`, one object per section
  (`{section, products:[{id, category, image, name, old_price, price, search_words}]}`), exported together as `catalog`.
  Every page imports `catalog`. Products have no SKU. Section routes are fixed folders under `src\app\sections\<section>`.
- **Cart:** React context (`src\app\api\AppContext.tsx`, `currentUserCart`) mirrored to `localStorage["cart"]`.
  Shape: `[{ userEmail, items: [{ name, image, price, quantity, section }] }]`. Items are keyed by **name**, not SKU.
  Add-to-cart lives in `src\components\shared\AddToCart.tsx`; the cart is loaded in `src\components\navbar\Cart\Cart.tsx`.
- **Login gate:** the cart only works with a next-auth session (Google/GitHub OAuth), which needs credentials we don't have.
- **Checkout:** there is no checkout page. The cart drawer (`CartDrawer.tsx`) shows a client-computed subtotal and a
  `CHECKOUT` button that does nothing.
- **Run:** `npm install`, `npm run dev`, port 3000. Runs without build errors (only warnings for missing Google Maps / Spoonacular keys).

### What was changed in `grocergo`

| Change | File |
|---|---|
| New checkout page: loads the widget, adapts the cart to `{sku, qty}`, shows server totals, Pay and success screen | `src\app\checkout\page.jsx` (new) |
| Shared catalog exported from our dataset | `src\data\promo-products.json` (new, generated) |
| Sections we cover read their products from that JSON; other sections are untouched | `src\components\shared\Catalog.js` |
| "Demo shopper" sign-in (no OAuth needed) | `src\app\api\auth\[...nextauth]\route.ts`, `src\components\navbar\Login\LoginPopUp.tsx` |
| Cart drawer `CHECKOUT` button links to `/checkout` | `src\components\navbar\Cart\CartDrawer.tsx` |
| Price labels show `₹` instead of `$` (one character each) | 14 component files |

Our categories map onto existing store sections: Beverages → beverages, Pantry → essentials, Dairy → cheeses-and-dairy,
Produce → fruits, Snacks → snacks, Bakery → bakery, Breakfast → full-fridge, Personal Care → cleaning.

The cart itself was not changed. It stays keyed by name; the checkout page maps names to SKUs using the exported JSON.

## Known limitations

- CSV files instead of a database; one process-wide lock around writes.
- Mock payment: "Pay" only confirms the order and reduces stock.
- Single store, single rules row.
- The LLM runs only at rebuild time; with `LLM_PROVIDER=none` (the default `.env`) offers use the top-scored candidate
  and a template message. The Anthropic and OpenAI paths are implemented but were not exercised with a real key.
- No auth on the API or `/admin`.
- Store sections we don't cover (offers, frozen, petshop, ...) still show the template's original products. They have no
  SKU, so the checkout page lists them as "not available for checkout in this demo" and leaves them out of the total.
- `/cart/apply` also accepts no code, so a cart without a promo can still be priced and paid.
- Offer copy never contains prices or percentages (the widget shows those from server data), so the fallback message is
  "Pairs with your Green Tea" rather than "…at 25% off!".
- There is no honey image in the template, so honey reuses the maple syrup picture.
