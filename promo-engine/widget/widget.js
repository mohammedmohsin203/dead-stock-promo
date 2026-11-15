/* Dead-stock promo checkout widget. Plain JS, no build step.
   The browser never computes prices: every amount shown comes from the promo API. */
(function () {
  "use strict";

  var cfg = null;
  var root = null;
  var state = { offer: null, totals: null, code: null, error: "", dismissed: {}, busy: false, seq: 0 };

  function inr(amount) {
    return "₹" + Number(amount).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function post(path, body) {
    return fetch(cfg.apiBase + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var detail = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
          throw new Error(detail);
        }
        return data;
      });
    }, function () {
      throw new Error("Offers are unavailable right now.");
    });
  }

  function cart() {
    return (cfg.getCart() || []).filter(function (item) { return item.sku && item.qty > 0; });
  }

  function qtyInCart(sku) {
    return cart().reduce(function (sum, item) { return item.sku === sku ? sum + item.qty : sum; }, 0);
  }

  function waitForCart(sku, minQty) {
    return new Promise(function (resolve, reject) {
      var started = Date.now();
      (function poll() {
        if (qtyInCart(sku) >= minQty) return resolve();
        if (Date.now() - started > 3000) return reject(new Error("Could not add the item to your cart."));
        setTimeout(poll, 50);
      })();
    });
  }

  function renderOffer(offer) {
    var card = el("div", "pw-card");
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "Special offer");

    var img = el("img", "pw-img");
    img.src = (cfg.imageBase || "") + offer.image;
    img.alt = offer.target_name;
    card.appendChild(img);

    var body = el("div", "pw-body");
    body.appendChild(el("div", "pw-message", offer.message));
    var title = el("div", "pw-title", offer.target_name);
    title.appendChild(el("span", "pw-badge", offer.discount_pct + "% off"));
    body.appendChild(title);

    var prices = el("div", "pw-prices");
    prices.appendChild(el("s", "pw-old", inr(offer.price)));
    prices.appendChild(el("span", "pw-new", inr(offer.new_price)));
    body.appendChild(prices);
    body.appendChild(el("div", "pw-reason", offer.reason));

    var actions = el("div", "pw-actions");
    var accept = el("button", "pw-btn", state.busy ? "Applying…" : "Add & apply");
    accept.type = "button";
    accept.disabled = state.busy;
    accept.addEventListener("click", function () { acceptOffer(offer); });
    var decline = el("button", "pw-link", "No thanks");
    decline.type = "button";
    decline.addEventListener("click", function () {
      state.dismissed[offer.code] = true;
      state.offer = null;
      render();
    });
    actions.appendChild(accept);
    actions.appendChild(decline);
    body.appendChild(actions);

    card.appendChild(body);
    return card;
  }

  function renderCodeForm() {
    var form = el("form", "pw-code");
    var label = el("label", "pw-code-label", "Have a code?");
    var input = el("input", "pw-input");
    input.name = "code";
    input.placeholder = "DEAD25-HNY500";
    input.autocomplete = "off";
    input.setAttribute("aria-label", "Promo code");
    var button = el("button", "pw-btn pw-btn-small", "Apply");
    button.type = "submit";
    form.appendChild(label);
    form.appendChild(input);
    form.appendChild(button);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (input.value.trim()) api.applyCode(input.value.trim());
    });
    return form;
  }

  function row(label, value, className) {
    var line = el("div", "pw-row" + (className ? " " + className : ""));
    line.appendChild(el("span", "", label));
    line.appendChild(el("span", "", value));
    return line;
  }

  function renderSummary(totals) {
    var box = el("div", "pw-summary");
    box.appendChild(row("Subtotal", inr(totals.subtotal)));
    if (totals.applied_code) {
      var discount = row("Discount (" + totals.applied_code + ")", "−" + inr(totals.discount), "pw-discount");
      var remove = el("button", "pw-link pw-remove", "remove");
      remove.type = "button";
      remove.addEventListener("click", function () {
        state.code = null;
        api.refresh();
      });
      discount.firstChild.appendChild(remove);
      box.appendChild(discount);
    }
    box.appendChild(row("Total", inr(totals.final_total), "pw-total"));
    return box;
  }

  function render() {
    // Looked up on every render: the host (e.g. React) may mount the container after init().
    root = typeof cfg.container === "string" ? document.querySelector(cfg.container) : cfg.container;
    if (!root) return;
    root.textContent = "";
    root.classList.add("pw-root");
    if (state.offer && !state.code) root.appendChild(renderOffer(state.offer));
    if (state.totals) {
      if (!state.code) root.appendChild(renderCodeForm());
      root.appendChild(renderSummary(state.totals));
    }
    if (state.error) {
      var error = el("div", "pw-error", state.error);
      error.setAttribute("role", "alert");
      root.appendChild(error);
    }
  }

  function setTotals(totals) {
    state.totals = totals;
    if (cfg.onTotals) cfg.onTotals(totals);
  }

  function priceCart(items) {
    return post("/cart/apply", { items: items, code: state.code }).catch(function (err) {
      if (!state.code) throw err;
      // The code no longer applies (expired, target removed, ...): explain, then price without it.
      state.error = err.message;
      state.code = null;
      return post("/cart/apply", { items: items, code: null });
    });
  }

  function acceptOffer(offer) {
    state.busy = true;
    state.error = "";
    render();
    var hadItem = qtyInCart(offer.target_sku) > 0;
    Promise.resolve(hadItem ? null : cfg.onAddItem(offer.target_sku))
      .then(function () { return waitForCart(offer.target_sku, 1); })
      .then(function () {
        state.busy = false;
        return api.applyCode(offer.code);
      })
      .catch(function (err) {
        state.busy = false;
        state.error = err.message;
        render();
      });
  }

  var api = {
    init: function (options) {
      cfg = options;
      cfg.apiBase = (cfg.apiBase || "").replace(/\/$/, "");
      state = { offer: null, totals: null, code: null, error: "", dismissed: {}, busy: false, seq: 0 };
      return api.refresh();
    },

    refresh: function () {
      if (!cfg) return Promise.resolve();
      var seq = ++state.seq;
      var items = cart();
      if (!items.length) {
        state.offer = null;
        state.code = null;
        state.error = "";
        setTotals(null);
        render();
        return Promise.resolve();
      }
      var hadCode = Boolean(state.code);
      if (!hadCode) state.error = "";
      return priceCart(items)
        .then(function (totals) {
          if (seq !== state.seq) return null;
          setTotals(totals);
          return state.code ? { offer: null } : post("/recommend", { items: items });
        })
        .then(function (data) {
          if (!data || seq !== state.seq) return;
          state.offer = data.offer && !state.dismissed[data.offer.code] ? data.offer : null;
          render();
        })
        .catch(function (err) {
          if (seq !== state.seq) return;
          state.error = err.message;
          state.offer = null;
          setTotals(null);
          render();
        });
    },

    applyCode: function (code) {
      state.code = String(code).trim().toUpperCase();
      state.error = "";
      return api.refresh();
    },

    pay: function () {
      if (!state.totals) return Promise.reject(new Error("Your cart has not been priced yet."));
      var customer = cfg.getCustomer ? cfg.getCustomer() || null : null;
      var order = { items: cart(), token: state.totals.token, customer: customer };
      return post("/order/confirm", order).then(function (result) {
        state.offer = null;
        state.code = null;
        state.totals = null;
        state.error = "";
        render();
        if (cfg.onPay) cfg.onPay(result);
        return result;
      }, function (err) {
        state.error = err.message;
        render();
        throw err;
      });
    },
  };

  window.PromoWidget = api;
})();
