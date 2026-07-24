"""Closer — the LLM layer (Phase 2).

The ONLY job of this module is language <-> structure translation on both ends of
the numpy engine. It never estimates a floor price or invents numbers; it turns a
seller message into `Signals` and turns the engine's recommendation into a human
iMessage.

Every function has two paths:
  • Runware (Claude via the native task API) when RUNWARE_API_KEY is set — primary.
  • A deterministic rules fallback when it isn't (or the call fails) — so the whole
    app still runs end-to-end offline, and a network blip never stalls a live demo.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from app import runware
from app.engine import Signals

MODELS = {"text": runware.MODEL}


# ── JSON helpers ─────────────────────────────────────────────────────────────
def _extract_json(s: str):
    """Pull the first JSON object/array out of a model response (fence-tolerant)."""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", s, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON found in model response: {s[:200]!r}")
    return json.loads(m.group(1))


def _json_call(system: str, user: str, images: Optional[list[str]] = None,
               max_tokens: int = 700) -> dict:
    """Ask for JSON, parse it, retrying once on a parse failure, then raise."""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    last_err: Optional[Exception] = None
    for attempt in range(2):
        raw = runware.text_inference(messages, images=images, max_tokens=max_tokens)
        try:
            return _extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": "That was not valid JSON. Respond with ONLY "
                                        "the JSON object, no prose, no code fences."})
    raise ValueError(f"model did not return valid JSON: {last_err}")


# ── Price parsing (shared by the rules fallback) ─────────────────────────────
def extract_price(text: str, asking: float) -> Optional[float]:
    """Best guess at the price the seller is stating, in absolute dollars.

    Handles "$15,200", "15200", "15.2k", "15k", and bare "15"/"12.4" (thousands).
    Returns the largest plausible price in the message (sellers quote high), or None.
    """
    cands: list[float] = []
    lo, hi = 0.30 * asking, 1.20 * asking
    # 15,200  /  $14,000
    for m in re.finditer(r"\$?\d{1,3}(?:,\d{3})+", text):
        cands.append(float(m.group(0).replace("$", "").replace(",", "")))
    # 15k / 15.2k
    for m in re.finditer(r"\$?(\d+(?:\.\d+)?)\s*[kK]\b", text):
        cands.append(float(m.group(1)) * 1000)
    # bare 14000 / 13500
    for m in re.finditer(r"(?<![\d,.$])\d{4,6}(?![\d,])", text):
        cands.append(float(m.group(0)))
    # bare 15 / 12.4  -> thousands
    for m in re.finditer(r"(?<![\d,.$kK])\b(\d{1,2}(?:\.\d+)?)\b(?![\d,kK])", text):
        cands.append(float(m.group(1)) * 1000)
    plausible = [c for c in cands if lo <= c <= hi]
    return max(plausible) if plausible else None


# ── 1. Listing parse ─────────────────────────────────────────────────────────
_LISTING_SYS = (
    "You extract structured facts from a used-car listing. Respond with ONLY a JSON "
    "object: {\"title\": str, \"asking\": number, \"year\": number|null, "
    "\"miles\": number|null, \"notes\": str}. asking is the listed price in dollars."
)


def parse_listing(text_or_url_context: str) -> dict:
    if runware.available():
        try:
            d = _json_call(_LISTING_SYS, text_or_url_context)
            d.setdefault("title", "Used car")
            return d
        except Exception:
            pass
    # Fallback: pull an asking price + a 4-digit year out of the text.
    asking = None
    for m in re.finditer(r"\$?\d{1,3}(?:,\d{3})+|\$\d{4,6}", text_or_url_context):
        asking = float(m.group(0).replace("$", "").replace(",", ""))
        break
    ym = re.search(r"\b(19|20)\d{2}\b", text_or_url_context)
    mm = re.search(r"([\d,]+)\s*(?:mi|miles|k\s*miles)", text_or_url_context, re.I)
    return {
        "title": text_or_url_context.strip()[:80] or "Used car",
        "asking": asking or 0,
        "year": int(ym.group(0)) if ym else None,
        "miles": int(mm.group(1).replace(",", "")) if mm else None,
        "notes": "",
    }


# ── 2. Classify seller message -> Signals ────────────────────────────────────
_CLASSIFY_SYS = """You translate ONE used-car seller message into structured negotiation signals.
You do NOT estimate any floor price. Respond with ONLY a JSON object:
{"seller_price": number|null, "concession_abs": number, "firmness": number,
 "bluff_claim": bool, "final_claim": bool, "walk_threat": bool}

Definitions:
- seller_price: the price the SELLER states in THIS message (dollars), else null.
- concession_abs: prev_seller_price minus seller_price, in dollars, else 0.
- firmness: 0..1, how firm/final the language is (soft "I could do" ~0.4, "lowest I'll go" ~0.85).
- bluff_claim: true if they cite other buyers/interest to pressure WITHOUT a real price drop.
- final_claim: true for "final offer", "lowest I'll go", "that's it".
- walk_threat: true if they threaten to end the conversation.
If a message is a bluff with no genuine price movement, set seller_price=null and concession_abs=0.

Examples:
Msg: "I could do 15,200." (prev 16000) -> {"seller_price":15200,"concession_abs":800,"firmness":0.45,"bluff_claim":false,"final_claim":false,"walk_threat":false}
Msg: "I've got someone coming to see it tomorrow, 15 is the lowest I'll go." (prev 15200) -> {"seller_price":null,"concession_abs":0,"firmness":0.85,"bluff_claim":true,"final_claim":true,"walk_threat":false}
Msg: "You're killing me. 14,000 and it's yours, final." (prev 15200) -> {"seller_price":14000,"concession_abs":1200,"firmness":0.8,"bluff_claim":false,"final_claim":true,"walk_threat":false}
"""

_BLUFF_KW = ("another buyer", "someone else", "other offers", "other people", "lots of interest",
             "coming to see", "coming to look", "interested party", "people interested",
             "have interest", "someone coming", "others interested", "cash buyer lined")
_FINAL_KW = ("final", "lowest i", "lowest i'll", "best i can", "take it or leave",
             "that's it", "that's my", "not a penny", "won't go lower", "can't go lower", "firm")
_WALK_KW = ("forget it", "never mind", "not interested", "walk away", "done talking",
            "i'll pass", "no deal", "waste of time")
_SOFT_KW = ("could do", "maybe", "might", "i guess", "open to", "flexible", "probably", "i suppose")


def _rules_classify(text: str, prev_seller_price: Optional[float], asking: float) -> Signals:
    t = text.lower()
    bluff = any(k in t for k in _BLUFF_KW)
    final = any(k in t for k in _FINAL_KW)
    walk = any(k in t for k in _WALK_KW)

    firmness = 0.5
    if final:
        firmness = 0.85
    if any(k in t for k in _SOFT_KW):
        firmness = min(firmness, 0.45)

    price = extract_price(text, asking)
    seller_price: Optional[float] = price
    concession = 0.0
    if price is not None and prev_seller_price is not None:
        concession = max(0.0, prev_seller_price - price)

    # Cheap talk: a bluff with no meaningful drop is treated as no movement, so the
    # engine's belief barely budges ("bluff called by math").
    meaningful_drop = (prev_seller_price is not None and seller_price is not None
                       and (prev_seller_price - seller_price) >= 0.02 * asking)
    if bluff and not meaningful_drop:
        seller_price = None
        concession = 0.0

    return Signals(seller_price=seller_price, concession_abs=concession,
                   firmness=firmness, bluff_claim=bluff, final_claim=final,
                   walk_threat=walk)


def classify_seller_message(text: str, prev_seller_price: Optional[float],
                            asking: float) -> Signals:
    if runware.available():
        try:
            user = (f"prev_seller_price: {prev_seller_price}\nasking: {asking}\n"
                    f"Seller message:\n{text}")
            d = _json_call(_CLASSIFY_SYS, user, max_tokens=300)
            return Signals(
                seller_price=(None if d.get("seller_price") in (None, "null")
                              else float(d["seller_price"])),
                concession_abs=float(d.get("concession_abs") or 0.0),
                firmness=float(d.get("firmness", 0.5)),
                bluff_claim=bool(d.get("bluff_claim", False)),
                final_claim=bool(d.get("final_claim", False)),
                walk_threat=bool(d.get("walk_threat", False)),
            )
        except Exception:
            pass
    return _rules_classify(text, prev_seller_price, asking)


# ── 3. Screenshot reading (vision) ───────────────────────────────────────────
#
# The second way to relay a seller, and the one people actually reach for: they
# are already in the thread with the seller, so screenshotting it is two taps and
# retyping it is a paragraph. `app/screenshot.py` merges, dedupes and orders what
# this returns; everything here is about one image.
#
# Asking for *both* sides of the conversation is deliberate even though only the
# seller's half reaches the engine. It is the cheapest way to make the model
# commit to who-said-what: a transcript that has to alternate is far harder to
# get backwards than a filtered list, and a seller/buyer swap would feed our own
# offers into the belief update as if the seller had made them.
_VISION_SYS = (
    "You read one screenshot from a phone and report exactly what is in it.\n"
    "\n"
    "It is usually a CHAT between a buyer (our user) and a private-party used-car "
    "seller — iMessage, SMS, Messenger, Facebook Marketplace, Craigslist, OfferUp. "
    "It may instead be a LISTING page for a car. It may be neither.\n"
    "\n"
    "Respond with ONLY a JSON object — no prose, no code fence:\n"
    '{"kind": "chat" | "listing" | "other",\n'
    ' "messages": [{"from": "seller" | "buyer", "text": "..."}],\n'
    ' "latest_seller_price": number | null,\n'
    ' "asking": number | null,\n'
    ' "title": string | null}\n'
    "\n"
    "Rules:\n"
    "- messages: top-to-bottom order, transcribed verbatim. Incoming bubbles "
    "(left-aligned, grey or white) are the SELLER. Outgoing bubbles (right-aligned, "
    "blue or green) are the BUYER. If alignment is ambiguous, the side quoting a "
    "price it wants FOR the car is the seller.\n"
    "- Transcribe message text only. Skip timestamps, delivery receipts, tapbacks, "
    "typing indicators, contact names, and every other piece of app chrome.\n"
    "- latest_seller_price: the most recent price the SELLER states, in dollars, "
    "else null. Never a monthly payment, never mileage, never a model year.\n"
    '- kind "listing": fill asking and title (e.g. "2008 Toyota Camry LE") and '
    "leave messages empty.\n"
    '- kind "other" — not a car chat, not a car listing, or too blurry to read: '
    "every field empty or null. Say so rather than guessing.\n"
    '- Numbers are plain dollars: 5400, not "$5,400".'
)

#: Roles the transcript may use. Anything else is dropped rather than guessed —
#: a mislabelled bubble is our own offer entering the belief update as theirs.
_ROLES = ("seller", "buyer")


def _as_price(value) -> Optional[float]:
    """A model-supplied dollar amount, or None. Tolerates "$5,400" and "null"."""
    if value in (None, "", "null", "none", "N/A"):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        cleaned = re.sub(r"[^\d.]", "", str(value))
        if not cleaned:
            return None
        try:
            price = float(cleaned)
        except ValueError:
            return None
    return price if price > 0 else None


def _normalize_read(payload: dict) -> dict:
    """Coerce the vision payload into the contract. Never raises on a sloppy shape."""
    kind = str(payload.get("kind") or "").strip().lower()
    if kind not in ("chat", "listing", "other"):
        kind = "chat" if payload.get("messages") else "other"

    messages: list[dict] = []
    for m in payload.get("messages") or []:
        if isinstance(m, str):                       # a bare list of strings
            text, who = m, "seller"
        elif isinstance(m, dict):
            text = m.get("text") or m.get("message") or m.get("value") or ""
            who = str(m.get("from") or m.get("role") or m.get("sender") or "").lower()
        else:
            continue
        text = " ".join(str(text).split()).strip()
        if not text:
            continue
        messages.append({"from": who if who in _ROLES else "seller", "text": text})

    latest = _as_price(payload.get("latest_seller_price"))
    if latest is None:                               # some runs only fill `asking`
        latest = _as_price(payload.get("seller_price"))
    title = payload.get("title")
    title = " ".join(str(title).split())[:80] or None if title else None
    return {"kind": kind, "messages": messages, "latest_seller_price": latest,
            "asking": _as_price(payload.get("asking")), "title": title}


def read_screenshot(image_ref: str, *, caption: Optional[str] = None) -> dict:
    """Read one screenshot. `image_ref` is a URL, a data URI, or raw base64.

    Returns `{kind, messages, latest_seller_price, asking, title}`. Requires
    Runware — there is no offline vision — so callers fall back to the text path
    when this raises.

    `caption` is whatever the user typed alongside the image. It is passed as
    context and explicitly fenced off from the transcript: "what do I say to
    this" must not come back as a line the seller said.
    """
    if not runware.available():
        raise runware.RunwareError("screenshot reading needs RUNWARE_API_KEY")
    ask = "Read this screenshot."
    if caption and caption.strip():
        ask += (f'\n\nThe user sent it with this note: "{caption.strip()[:300]}"\n'
                "That note is context from the user, NOT part of the screenshot. "
                "Do not transcribe it as a message.")
    return _normalize_read(_json_call(_VISION_SYS, ask, images=[image_ref],
                                      max_tokens=900))


def extract_from_screenshot(image_ref: str) -> dict:
    """Back-compat shape: `{seller_messages, latest_seller_price}`.

    Kept because the Phase-1 gate (`python -m app.llm --vision`) and anything
    written against it should keep working; `read_screenshot` is the real one.
    """
    d = read_screenshot(image_ref)
    return {"seller_messages": [m["text"] for m in d["messages"]
                                if m["from"] == "seller"],
            "latest_seller_price": d["latest_seller_price"]}


# ── 4. Draft the coach's iMessage ────────────────────────────────────────────
_DRAFT_SYS = """You are Closer, a sharp negotiation coach texting a friend who is buying a used car.
Write a short iMessage (<= 3 short paragraphs). Be confident and concrete. Use ONLY numbers
present in the data you're given — never invent a price or a floor. End with ONE ready-to-send
line the user can copy verbatim to the seller, in quotes. Tone: sharp friend, no corporate voice,
at most one emoji. Respond with ONLY the message text (no JSON, no preamble)."""


def _money(x) -> str:
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return str(x)


def _rules_draft(rec: dict, sig: Signals, research: dict, state: dict) -> str:
    action = rec["action"]
    offer, floor = rec["offer"], rec.get("floor_point_est")
    pct = int(round(rec.get("p_accept", 0) * 100))
    if action == "COUNTER":
        return (f"Counter {_money(offer)} and hold there. Their floor reads ~{_money(floor)}, "
                f"so there's ~{pct}% they take {_money(offer)}.\n\n"
                f"Send this: \"{_money(offer)}, cash, I can do it today. That's my number.\"")
    if action == "HOLD":
        return (f"That's pressure, not a real move — the number didn't budge. Don't chase it. "
                f"Hold at {_money(offer)} and let them come back.\n\n"
                f"Send this: \"Appreciate it, but {_money(offer)} is where I'm at. Let me know.\"")
    if action == "WALK":
        R = research.get("R") or offer
        return (f"Their floor is sitting above your walk-away of {_money(R)}. This one isn't "
                f"worth chasing — be ready to leave.\n\n"
                f"Send this: \"I get it, but {_money(R)} is my ceiling given what it needs. "
                f"No worries if it doesn't work.\"")
    if action == "ACCEPT":
        return (f"Take it. {_money(offer)} is at or under fair value and beats your best counter's "
                f"odds. Lock it in before they change their mind. 🤝\n\n"
                f"Send this: \"Deal. {_money(offer)}, let's do it.\"")
    return f"Recommendation: {action} at {_money(offer)}."


def draft_coach_message(recommendation: dict, signals: Signals, research: dict,
                        state: dict) -> str:
    if runware.available():
        try:
            payload = {
                "recommendation": recommendation,
                "signals": signals.as_dict(),
                "research": {k: research.get(k) for k in
                             ("fair_value", "R", "V", "hidden_costs", "red_flags",
                              "facts", "sources", "confidence")},
                "seller_last_price": state.get("last_seller_price"),
                "your_last_offer": state.get("last_user_offer"),
            }
            user = ("Write the coach message for this negotiation turn. Data:\n"
                    + json.dumps(payload, default=str))
            msgs = [{"role": "system", "content": _DRAFT_SYS},
                    {"role": "user", "content": user}]
            return runware.text_inference(msgs, max_tokens=350).strip()
        except Exception:
            pass
    return _rules_draft(recommendation, signals, research, state)


# ── smoke test: python -m app.llm  [--smoke] [--models] ──────────────────────
_CANON = [
    ("I could do 15,200.", 16000),
    ("I've got someone coming to see it tomorrow, 15 is the lowest I'll go.", 15200),
    ("You're killing me. 14,000 and it's yours, final.", 15200),
]

if __name__ == "__main__":
    import sys

    if "--models" in sys.argv:
        for m in runware.list_models(limit=60):
            print(m)
        sys.exit(0)

    if "--vision" in sys.argv:
        # Dev 1 Phase-1 gate: prove the A1 image path end to end.
        #   python -m app.llm --vision tests/fixtures/chat1.png
        import base64
        import pathlib

        path = pathlib.Path(sys.argv[sys.argv.index("--vision") + 1])
        mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        data_uri = (f"data:{mime};base64,"
                    + base64.b64encode(path.read_bytes()).decode())
        print(f"reading {path} ({path.stat().st_size:,} bytes) via "
              f"{'RUNWARE' if runware.available() else 'NO KEY — cannot run'}")
        out = read_screenshot(data_uri)
        print("kind          :", out["kind"])
        for m in out["messages"]:
            print(f"  {m['from']:>6}: {m['text']}")
        print("latest price  :", out["latest_seller_price"])
        print("asking / title:", out["asking"], "/", out["title"])
        sys.exit(0)

    if "--smoke" in sys.argv:
        print("Runware available:", runware.available(), "| model:", runware.MODEL)
        txt = runware.text_inference(
            [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=10)
        print("live ping ->", repr(txt))
        sys.exit(0)

    print(f"classify path: {'RUNWARE' if runware.available() else 'RULES fallback'}\n")
    for text, prev in _CANON:
        sig = classify_seller_message(text, prev, 16000)
        print(f"  {text!r}\n    -> {sig.as_dict()}\n")
