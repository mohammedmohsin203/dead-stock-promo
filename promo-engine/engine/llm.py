"""LLM picks the offer and writes the copy. Called only during rebuild, never at checkout."""
import json
import logging
import os
import re
import threading

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10
DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4o-mini", "groq": "openai/gpt-oss-120b"}
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Set on the first rate-limit error; the rest of the rebuild then uses the fallback instead of failing 60 times.
_rate_limited = threading.Event()

SYSTEM_PROMPT = """You choose one promotional add-on for an online grocery shopper.
You get the product in the shopper's cart (the trigger) and a short list of candidate products.

Rules:
- Choose only from the given candidates. Never invent a product or SKU.
- Prefer complements (things used together with the trigger) over substitutes.
- Respect diet signals: do not pair sugary items with sugar-free or diabetic products.
- Never mention or invent prices, discounts, percentages or any numbers in "message".
- "message": at most 12 words, friendly, written to the shopper.
- "reason": at most 10 words, factual, using only the stock facts provided.

Reply with one JSON object and nothing else:
{"sku": "...", "message": "...", "reason": "..."}"""


def short_name(name: str) -> str:
    return re.sub(r"\s*(\(.*\)|\d+\s?(g|kg|ml|l)\b.*)$", "", name, flags=re.IGNORECASE).strip() or name


def fallback_message(trigger) -> str:
    return f"Pairs with your {short_name(trigger['name'])}"


def fallback_reason(candidate, rules: dict) -> str:
    if candidate["days_unsold"] >= rules["dead_stock_days"]:
        return f"{candidate['days_unsold']} days unsold, {candidate['stock']} in stock"
    return f"Expires in {candidate['days_to_expiry']} days, {candidate['stock']} in stock"


def _fallback(trigger, candidates, rules) -> dict:
    top = candidates[0]
    return {"sku": top["sku"], "message": fallback_message(trigger), "reason": fallback_reason(top, rules),
            "source": "template"}


def _user_prompt(trigger, candidates) -> str:
    fields = ["sku", "name", "category", "tags", "pairs_with", "avoid_with", "days_unsold", "stock", "days_to_expiry"]
    return json.dumps({
        "trigger": {k: trigger[k] for k in ("name", "category", "tags")},
        "candidates": [{k: c[k] for k in fields} for c in candidates],
    }, default=int)


def _call_anthropic(model: str, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=0)
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined the request")
    return "".join(block.text for block in response.content if block.type == "text")


def _call_groq(model: str, prompt: str) -> str:
    return _call_openai(model, prompt, {"reasoning_effort": "low"},
                        base_url=GROQ_BASE_URL, api_key=os.getenv("API_KEY"))


def _call_openai(model: str, prompt: str, request_options: dict | None = None, **client_options) -> str:
    import openai

    client = openai.OpenAI(timeout=TIMEOUT_SECONDS, max_retries=0, **client_options)
    response = client.chat.completions.create(
        model=model,
        **(request_options or {}),
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def _parse(text: str, candidates, fallback: dict) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    data = json.loads(match.group(0)) if match else {}
    sku = str(data.get("sku", "")).strip()
    if sku not in {c["sku"] for c in candidates}:
        return fallback
    message = str(data.get("message", "")).strip()
    reason = str(data.get("reason", "")).strip()
    # The LLM never sets prices: reject copy that carries any number, % or currency.
    if not message or len(message.split()) > 12 or re.search(r"[\d%₹$]|\brs\b", message, flags=re.IGNORECASE):
        message = fallback["message"]
    # Keep the reason factual: it must cite a stock number, otherwise the template reason is used.
    if not reason or len(reason.split()) > 10 or not re.search(r"\d", reason):
        reason = None
    return {"sku": sku, "message": message, "reason": reason, "source": "llm"}


def start_rebuild() -> None:
    _rate_limited.clear()


def provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "none").strip().lower()


def pick_offer(trigger, candidates: list[dict], rules: dict) -> dict:
    """Returns {"sku", "message", "reason", "source"}; sku is always one of the candidates."""
    fallback = _fallback(trigger, candidates, rules)
    provider = provider_name()
    call = {"anthropic": _call_anthropic, "openai": _call_openai, "groq": _call_groq}.get(provider)
    if call is None or _rate_limited.is_set():
        return fallback
    try:
        model = os.getenv("LLM_MODEL") or DEFAULT_MODELS[provider]
        picked = _parse(call(model, _user_prompt(trigger, candidates)), candidates, fallback)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            if not _rate_limited.is_set():
                log.warning("LLM rate limit reached; remaining offers use the template message.")
            _rate_limited.set()
        else:
            log.warning("LLM pick failed for %s, using fallback: %s", trigger["sku"], str(exc)[:200])
        return fallback
    if picked["reason"] is None:
        chosen = next(c for c in candidates if c["sku"] == picked["sku"])
        picked["reason"] = fallback_reason(chosen, rules)
    return picked
