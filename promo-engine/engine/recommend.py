import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import llm
from .config import IST, cache_dir, load_rules, write_atomic
from .copurchase import load_copurchase
from .index import ProductIndex
from .loader import load_catalog, mentions
from .pricing import price_promo

TOP_CANDIDATES = 5
log = logging.getLogger(__name__)


def _candidates(trigger, catalog, index, copurchase, rules, now) -> list[dict]:
    similarity = index.related(trigger)
    pool = set(similarity) | set(copurchase.partners(trigger["sku"]))
    pool |= {sku for sku, p in catalog.iterrows() if mentions(p["pairs_with"], trigger)}

    scored = []
    for sku in pool:
        if sku not in catalog.index:
            continue
        target = catalog.loc[sku]
        if (
            sku == trigger["sku"]
            or target["stock"] <= 0
            or not target["is_dead"]
            or target["category"] == trigger["category"]
            or mentions(target["avoid_with"], trigger)
        ):
            continue
        promo = price_promo(target, rules, now)
        if promo is None:
            continue
        pairs_match = mentions(target["pairs_with"], trigger)
        bought_together = copurchase.copurchase_score(trigger["sku"], sku)
        similar = similarity.get(sku, 0.0)
        stuck = float(target["stuck"])
        fit = 0.4 * pairs_match + 0.35 * bought_together + 0.25 * similar
        final = 0.5 * fit + 0.5 * stuck
        scored.append({
            **target.to_dict(),
            "promo": promo,
            "score": round(final, 4),
            "explain": {
                "pairs_match": bool(pairs_match),
                "copurchase": round(bought_together, 3),
                "similarity": round(similar, 3),
                "fit": round(fit, 3),
                "stuck": round(stuck, 3),
            },
        })
    return sorted(scored, key=lambda c: c["score"], reverse=True)[:TOP_CANDIDATES]


def _offer(trigger, candidate, message, reason, source) -> dict:
    return {
        "trigger_sku": trigger["sku"],
        "target_sku": candidate["sku"],
        "target_name": candidate["name"],
        "image": candidate["image"],
        **candidate["promo"],
        "message": message,
        "reason": reason,
        "score": candidate["score"],
        "explain": candidate["explain"],
        "source": source,
    }


def _offers_for(trigger, candidates, rules, picks: dict) -> list[dict]:
    """Ranked offers for one trigger: the LLM's pick first, then the other candidates as backups."""
    if not candidates:
        return []
    by_sku = {c["sku"]: c for c in candidates}
    # An LLM pick is reused while the trigger's shortlist is unchanged, so repeat rebuilds
    # (e.g. after a rules change) don't spend the provider's rate limit again.
    key = f"{trigger['sku']}|{','.join(by_sku)}"
    if key in picks:
        pick = {**picks[key], "reason": llm.fallback_reason(by_sku[picks[key]["sku"]], rules), "source": "llm"}
    else:
        pick = llm.pick_offer(trigger, candidates, rules)
        if pick["source"] == "llm":
            picks[key] = {"sku": pick["sku"], "message": pick["message"]}
    # Guardrail: only accept a SKU that was actually offered to the LLM.
    chosen = by_sku.get(pick["sku"], candidates[0])
    offers = [_offer(trigger, chosen, pick["message"], pick["reason"], pick["source"])]
    offers += [
        _offer(trigger, c, llm.fallback_message(trigger), llm.fallback_reason(c, rules), "backup")
        for c in candidates if c["sku"] != chosen["sku"]
    ]
    return offers


def promos_path():
    return cache_dir() / "promos.json"


def _load_picks() -> dict:
    path = cache_dir() / "llm_picks.json"
    if llm.provider_name() == "none" or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild() -> dict:
    """Offline pipeline: CSVs -> loader -> Chroma -> retrieve -> score -> LLM -> pricing -> promos.json."""
    started = time.perf_counter()
    rules = load_rules()
    catalog = load_catalog(rules)
    index = ProductIndex(catalog)
    copurchase = load_copurchase()
    now = datetime.now(IST)

    triggers = [row for _, row in catalog[catalog["stock"] > 0].iterrows()]
    shortlists = [_candidates(t, catalog, index, copurchase, rules, now) for t in triggers]
    picks = _load_picks()
    llm.start_rebuild()
    with ThreadPoolExecutor(max_workers=2) as pool:
        ranked = list(pool.map(lambda pair: _offers_for(pair[0], pair[1], rules, picks), zip(triggers, shortlists)))
    if picks:
        write_atomic(cache_dir() / "llm_picks.json", json.dumps(picks, indent=2, ensure_ascii=False))

    promos = {
        "built_at": now.isoformat(timespec="seconds"),
        "offers": {t["sku"]: offers for t, offers in zip(triggers, ranked) if offers},
    }
    promos["took_ms"] = int((time.perf_counter() - started) * 1000)
    promos["llm_written"] = sum(1 for offers in promos["offers"].values() if offers[0]["source"] == "llm")
    log.info("Rebuilt %d offers in %d ms; %d with LLM-written copy, %d with the template message.",
             len(promos["offers"]), promos["took_ms"], promos["llm_written"],
             len(promos["offers"]) - promos["llm_written"])
    write_atomic(promos_path(), json.dumps(promos, indent=2, ensure_ascii=False, default=int))
    return promos


def load_promos() -> dict | None:
    """Cached offers, or None if there is no usable cache (missing, older format, or an offer expired)."""
    path = promos_path()
    if not path.exists():
        return None
    promos = json.loads(path.read_text(encoding="utf-8"))
    offers = [o for ranked in promos["offers"].values() for o in ranked]
    now = datetime.now(IST)
    stale = any("explain" not in o or datetime.fromisoformat(o["expires_at"]) <= now for o in offers)
    return None if stale else promos


def recommend_for_cart(items: dict[str, int], promos: dict, catalog, rules: dict,
                       now: datetime | None = None) -> dict | None:
    """Request-time pick: cache lookup plus whole-cart guardrails. No model calls."""
    now = now or datetime.now(IST)
    cart_products = [catalog.loc[sku] for sku in items if sku in catalog.index]
    best = None
    for sku in items:
        for offer in promos["offers"].get(sku, []):
            target = catalog.loc[offer["target_sku"]]
            in_cart = items.get(offer["target_sku"], 0)
            if (
                in_cart >= rules["max_discounted_units"]
                or target["stock"] <= in_cart
                or datetime.fromisoformat(offer["expires_at"]) <= now
                or any(mentions(target["avoid_with"], p) for p in cart_products)
            ):
                continue
            if best is None or offer["score"] > best["score"]:
                best = offer
    return best
