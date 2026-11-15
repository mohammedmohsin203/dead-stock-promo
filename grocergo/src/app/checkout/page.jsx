"use client";
import { useEffect, useRef, useState } from "react";
import Script from "next/script";
import Image from "next/image";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { useAppContext } from "@/app/api/AppContext";
import products from "@/data/promo-products.json";

const PROMO_API = process.env.NEXT_PUBLIC_PROMO_API || "http://localhost:8000";
const bySku = Object.fromEntries(products.map((p) => [p.sku, p]));
const skuByName = Object.fromEntries(products.map((p) => [p.name, p.sku]));
const rupees = (amount) => `₹${Number(amount).toFixed(2)}`;

export default function CheckoutPage() {
  const { data: session, status } = useSession();
  const email = session?.user?.email;
  const { currentUserCart, setCurrentUserCart, setTotalCartItems, setLoginPopUp } = useAppContext();
  const items = currentUserCart?.items ?? [];
  const [totals, setTotals] = useState(null);
  const [paid, setPaid] = useState(null);
  const [paying, setPaying] = useState(false);
  const widgetReady = useRef(false);

  // The store cart is keyed by product name; the promo engine needs {sku, qty}.
  const cartRef = useRef(items);
  cartRef.current = items;
  const getCart = () =>
    cartRef.current
      .filter((item) => skuByName[item.name])
      .map((item) => ({ sku: skuByName[item.name], qty: item.quantity }));

  const saveCart = (nextItems) => {
    cartRef.current = nextItems;
    setCurrentUserCart({ userEmail: email, items: nextItems });
    setTotalCartItems(nextItems.length);
    const stored = JSON.parse(localStorage.getItem("cart") || "[]");
    localStorage.setItem(
      "cart",
      JSON.stringify(stored.map((cart) => (cart.userEmail === email ? { ...cart, items: nextItems } : cart)))
    );
  };

  const changeQty = (sku, delta) =>
    saveCart(
      cartRef.current
        .map((item) => (skuByName[item.name] === sku ? { ...item, quantity: item.quantity + delta } : item))
        .filter((item) => item.quantity > 0)
    );

  const addItem = (sku) => {
    const product = bySku[sku];
    if (cartRef.current.some((item) => item.name === product.name)) return changeQty(sku, 1);
    saveCart([
      ...cartRef.current,
      { name: product.name, image: product.image, price: product.price, quantity: 1, section: product.section },
    ]);
  };

  // The widget keeps the callbacks from init(), so route them through a ref to avoid stale closures.
  const handlers = useRef({});
  handlers.current = {
    email,
    addItem,
    onPay: (result) => {
      setPaid(result);
      saveCart([]);
    },
  };

  const initWidget = () => {
    window.PromoWidget.init({
      apiBase: PROMO_API,
      container: "#promo-widget",
      getCart,
      getCustomer: () => handlers.current.email,
      onAddItem: (sku) => handlers.current.addItem(sku),
      onTotals: setTotals,
      onPay: (result) => handlers.current.onPay(result),
    });
    widgetReady.current = true;
  };

  const cartKey = items.map((item) => `${item.name}:${item.quantity}`).join("|");
  useEffect(() => {
    if (widgetReady.current) window.PromoWidget.refresh();
  }, [cartKey]);

  const pay = () => {
    setPaying(true);
    window.PromoWidget.pay()
      .catch(() => {})
      .finally(() => setPaying(false));
  };

  const unsupported = items.filter((item) => !skuByName[item.name]);

  return (
    <main className="w-full max-w-3xl mx-auto min-h-screen px-6 py-10 text-green-5">
      <link rel="stylesheet" href={`${PROMO_API}/widget/widget.css`} />
      <Script src={`${PROMO_API}/widget/widget.js`} onReady={initWidget} />
      <h1 className="font-black text-3xl tracking-wider mb-6">CHECKOUT</h1>

      {paid ? (
        <section className="rounded-2xl bg-green-1/20 border border-green-2 p-8 text-center space-y-3">
          <p className="text-2xl font-black text-green-4">
            Paid {rupees(paid.paid_total)} · Order {paid.order_id}
          </p>
          <p className="font-bold">
            Stock left:{" "}
            {Object.entries(paid.stock_after)
              .map(([sku, stock]) => `${bySku[sku]?.name ?? sku} ${stock}`)
              .join(" · ")}
          </p>
          <Link href="/" className="inline-block rounded-full bg-green-4 text-white font-black px-6 py-2">
            Continue shopping
          </Link>
        </section>
      ) : status !== "authenticated" ? (
        <section className="rounded-2xl border p-8 text-center space-y-4">
          <p className="font-bold">Sign in to see your cart.</p>
          <button
            onClick={() => setLoginPopUp(true)}
            className="rounded-full bg-green-4 text-white font-black px-6 py-2"
          >
            Sign in
          </button>
        </section>
      ) : items.length === 0 ? (
        <section className="rounded-2xl border p-8 text-center space-y-4">
          <p className="font-bold">Your cart is empty.</p>
          <Link href="/sections/beverages" className="inline-block rounded-full bg-green-4 text-white font-black px-6 py-2">
            Browse beverages
          </Link>
        </section>
      ) : (
        <section className="rounded-2xl border bg-white p-6 space-y-6">
          <ul className="space-y-3">
            {(totals?.lines ?? []).map((line) => (
              <li key={line.sku} className="flex items-center gap-4">
                <Image
                  src={bySku[line.sku]?.image}
                  alt={line.name}
                  width={56}
                  height={56}
                  className="bg-green-1/20 rounded-bl-xl rounded-tr-xl p-1.5 w-14 h-14"
                />
                <div className="grow">
                  <p className="font-black">{line.name}</p>
                  <p className="text-sm text-gray-500">{rupees(line.unit_price)} each</p>
                </div>
                <div className="flex items-center text-lg">
                  <button aria-label={`remove one ${line.name}`} onClick={() => changeQty(line.sku, -1)} className="px-2">
                    -
                  </button>
                  <span className="text-sm px-1">{line.qty}</span>
                  <button aria-label={`add one ${line.name}`} onClick={() => changeQty(line.sku, 1)} className="px-2">
                    +
                  </button>
                </div>
                <div className="w-28 text-right">
                  <p className="font-black tracking-wider">{rupees(line.line_total)}</p>
                  {line.discount > 0 && <p className="text-xs text-green-3 font-bold">saved {rupees(line.discount)}</p>}
                </div>
              </li>
            ))}
          </ul>
          {unsupported.length > 0 && (
            <p className="text-sm text-gray-500">
              Not available for checkout in this demo: {unsupported.map((item) => item.name).join(", ")}
            </p>
          )}

          <div id="promo-widget" />

          <button
            onClick={pay}
            disabled={!totals || paying}
            className="w-full flex justify-center rounded-full bg-green-2 disabled:opacity-50 active:translate-y-[1px] transition duration-100"
          >
            <span className="font-black text-white tracking-wider p-3">
              {totals ? `Pay ${rupees(totals.final_total)}` : "Calculating total…"}
            </span>
          </button>
        </section>
      )}
    </main>
  );
}
