"""Agentic product research (Phase 4) — Closer values the car itself.

There is no human expert in the loop. Closer runs a bounded ReAct-style research
loop with real tools and returns the same valuation contract the rest of the app
already consumes, plus the citations it earned:

    {fair_value, hidden_costs:[{item, cost}], red_flags:[str],
     facts:{year, make, model, trim, miles, asking},
     confidence: low|med|high, sources:[{title, url, note}],
     reasoning: str, steps:[...]}

From which the negotiation inputs are derived:
    V = fair_value                                  (market fair value)
    R = fair_value - sum(hidden_costs)              (walk-away, floored at 0.65*asking)

The loop
--------
Step 0 (deterministic, always): fetch the listing URL and strip it to text. That
text seeds the transcript, so even a zero-tool run has real facts to work from.

Then up to RESEARCH_MAX_STEPS iterations of:
    model -> {"tool": "web_search", "query": "..."}   -> top-N {title, url, snippet}
    model -> {"tool": "fetch_page", "url": "..."}     -> stripped text (cap 8k)
    model -> {"tool": "finish", ...payload}           -> done

Every layer degrades instead of failing:
  • RESEARCH_MODE=mock       -> canned demo payload, instant, no network.
  • no RUNWARE_API_KEY       -> deterministic heuristic valuation off the listing text.
  • search provider blocked  -> the tool returns an empty result set with a note;
                                the model keeps going and lowers its confidence.
  • model never calls finish -> heuristic payload, confidence "low".

Blocking by design (httpx sync, like the rest of the app). A research run takes
20-40s, so callers must not run it on the event loop: `await asyncio.to_thread(
research.run_research, link)`, or inline in a Vercel function with maxDuration
raised (see README / vercel.json).
"""

from __future__ import annotations

import html as htmlmod
import json
import os
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Callable, Optional

import httpx

from app import runware

RESEARCH_MODE = os.getenv("RESEARCH_MODE", "live").strip().lower()
RESEARCH_MAX_STEPS = int(os.getenv("RESEARCH_MAX_STEPS", "6"))
RESEARCH_TIMEOUT_S = float(os.getenv("RESEARCH_TIMEOUT_S", "20"))
PAGE_CHAR_CAP = int(os.getenv("RESEARCH_PAGE_CHARS", "8000"))
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "ddg").strip().lower()
SEARCH_RESULTS = int(os.getenv("SEARCH_RESULTS", "5"))
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class ResearchError(RuntimeError):
    pass


# ── Canned payload for RESEARCH_MODE=mock (the demo car) ─────────────────────
MOCK_PAYLOAD: dict = {
    "fair_value": 14200,
    "hidden_costs": [{"item": "timing belt service due", "cost": 1200}],
    "red_flags": ["no service records", "vague condition wording",
                  "priced ~13% over comparable private-party listings"],
    "facts": {"year": 2019, "make": "Mazda", "model": "CX-5",
              "trim": "Touring AWD", "miles": 68000, "asking": 16000},
    "confidence": "high",
    "sources": [
        {"title": "2019 Mazda CX-5 Touring AWD private party value",
         "url": "https://www.kbb.com/mazda/cx-5/2019/touring/",
         "note": "private-party range $13.4k-$14.6k at 68k miles"},
        {"title": "Used 2019 Mazda CX-5 Touring listings near you",
         "url": "https://www.cars.com/shopping/results/?stock_type=used&makes[]=mazda",
         "note": "6 comparable listings, median asking $14,450"},
        {"title": "CX-5 2.5L maintenance schedule",
         "url": "https://www.mazdausa.com/owners/maintenance-schedules",
         "note": "timing/accessory belt service falls due near 60-70k miles"},
    ],
    "reasoning": ("Comparable private-party CX-5 Touring AWDs at 60-75k miles cluster "
                  "at $13.4k-$14.6k; this one is asking $16,000 with no service records "
                  "and a belt service coming due, so fair value lands at $14,200 and the "
                  "deferred maintenance comes straight off the walk-away."),
    "steps": [
        {"tool": "fetch_page", "arg": "<listing>", "note": "listing facts extracted"},
        {"tool": "web_search", "arg": "2019 Mazda CX-5 Touring AWD 68k private party value",
         "note": "5 results"},
        {"tool": "web_search", "arg": "2019 Mazda CX-5 68000 miles common problems",
         "note": "5 results"},
    ],
}


# ── HTML -> text ─────────────────────────────────────────────────────────────
class _Stripper(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}
    _BREAK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._depth += 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth:
            self._depth -= 1
        elif tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._depth and data.strip():
            self.parts.append(data.strip())
            self.parts.append(" ")


def html_to_text(html: str, cap: int = PAGE_CHAR_CAP) -> str:
    """Strip markup to readable text, collapse whitespace, truncate to `cap`."""
    s = _Stripper()
    try:
        s.feed(html)
    except Exception:  # noqa: BLE001 — malformed markup must never kill a run
        pass
    text = "".join(s.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:cap]


# ── Tool: fetch_page ─────────────────────────────────────────────────────────
def fetch_page(url: str, *, cap: int = PAGE_CHAR_CAP) -> dict:
    """GET a URL and return {url, text, error}. Never raises."""
    if not re.match(r"^https?://", url or ""):
        return {"url": url, "text": "", "error": "not an http(s) url"}
    try:
        r = httpx.get(url, headers={"User-Agent": _UA, "Accept-Language": "en-US,en"},
                      timeout=RESEARCH_TIMEOUT_S, follow_redirects=True)
    except httpx.HTTPError as e:
        return {"url": url, "text": "", "error": f"fetch failed: {e}"}
    if r.status_code >= 400:
        return {"url": url, "text": "", "error": f"HTTP {r.status_code}"}
    ctype = r.headers.get("content-type", "")
    body = r.text if "html" in ctype or "text" in ctype or not ctype else ""
    if not body:
        return {"url": url, "text": "", "error": f"unsupported content-type {ctype!r}"}
    return {"url": url, "text": html_to_text(body, cap), "error": None}


# ── Tool: web_search (provider-swappable, keyless by default) ────────────────
def _unwrap_ddg(href: str) -> str:
    href = htmlmod.unescape(href or "")
    if "uddg=" in href:
        q = urllib.parse.urlparse(href).query
        target = urllib.parse.parse_qs(q).get("uddg", [""])[0]
        if target:
            return target
    return f"https:{href}" if href.startswith("//") else href


def _is_ad(url: str) -> bool:
    """DDG injects sponsored rows as duckduckgo.com/y.js?ad_domain=... — drop them."""
    return "duckduckgo.com/y.js" in url or "ad_provider=" in url or "ad_domain=" in url


def _tags_to_text(fragment: str) -> str:
    return html_to_text(fragment, cap=400).replace("\n", " ").strip()


def _search_ddg(query: str, n: int) -> list[dict]:
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": query},
                   headers={"User-Agent": _UA}, timeout=RESEARCH_TIMEOUT_S,
                   follow_redirects=True)
    r.raise_for_status()
    html = r.text
    links = re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                       html, re.S)
    snips = re.findall(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.S)
    out: list[dict] = []
    for i, (href, title) in enumerate(links):
        url = _unwrap_ddg(href)
        if _is_ad(url):
            continue
        out.append({
            "title": _tags_to_text(title),
            "url": url,
            "snippet": _tags_to_text(snips[i]) if i < len(snips) else "",
        })
        if len(out) >= n:
            break
    return out


def _search_brave(query: str, n: int) -> list[dict]:
    r = httpx.get("https://api.search.brave.com/res/v1/web/search",
                  params={"q": query, "count": n},
                  headers={"X-Subscription-Token": BRAVE_API_KEY,
                           "Accept": "application/json"},
                  timeout=RESEARCH_TIMEOUT_S)
    r.raise_for_status()
    results = (r.json().get("web") or {}).get("results") or []
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": _tags_to_text(x.get("description", ""))} for x in results[:n]]


def _search_serper(query: str, n: int) -> list[dict]:
    r = httpx.post("https://google.serper.dev/search",
                   headers={"X-API-KEY": SERPER_API_KEY,
                            "Content-Type": "application/json"},
                   json={"q": query, "num": n}, timeout=RESEARCH_TIMEOUT_S)
    r.raise_for_status()
    return [{"title": x.get("title", ""), "url": x.get("link", ""),
             "snippet": x.get("snippet", "")}
            for x in (r.json().get("organic") or [])[:n]]


def web_search(query: str, *, n: int = SEARCH_RESULTS) -> dict:
    """Search the web. Returns {query, results, error}. Never raises.

    Provider order: whatever SEARCH_PROVIDER names, then keyless DuckDuckGo. A
    blocked/rate-limited provider yields results=[] and a note — the agent is told
    to keep going and lower its confidence rather than abort the run.
    """
    if not (query or "").strip():
        return {"query": query, "results": [], "error": "empty query"}
    order = [SEARCH_PROVIDER]
    if SEARCH_PROVIDER != "ddg":
        order.append("ddg")
    last_err = None
    for provider in order:
        try:
            if provider == "brave" and BRAVE_API_KEY:
                return {"query": query, "results": _search_brave(query, n), "error": None}
            if provider == "serper" and SERPER_API_KEY:
                return {"query": query, "results": _search_serper(query, n), "error": None}
            if provider == "ddg":
                return {"query": query, "results": _search_ddg(query, n), "error": None}
        except Exception as e:  # noqa: BLE001 — a dead search must not kill the run
            last_err = e
    return {"query": query, "results": [],
            "error": f"search unavailable ({last_err})" if last_err else "no search provider"}


# ── The agent loop ───────────────────────────────────────────────────────────
_SYSTEM = """You are Closer's product-research agent. You value ONE used car for a buyer who is
about to negotiate. You are the only source of valuation truth in this system, so your number has
to be defensible from evidence you actually gathered — never from vibes.

You work in a loop. Each turn respond with ONLY a JSON object, one of:

  {"thought": "<one short line>", "tool": "web_search", "query": "<search query>"}
  {"thought": "<one short line>", "tool": "fetch_page", "url": "<https url>"}
  {"thought": "<one short line>", "tool": "finish",
   "fair_value": <number>,
   "hidden_costs": [{"item": "<short>", "cost": <number>}],
   "red_flags": ["<short>", ...],
   "facts": {"year": <number|null>, "make": "<str>", "model": "<str>",
             "trim": "<str>", "miles": <number|null>, "asking": <number>},
   "confidence": "low"|"med"|"high",
   "sources": [{"title": "<str>", "url": "<str>", "note": "<what it established>"}],
   "reasoning": "<2-3 sentences a buyer could repeat to the seller>"}

Rules:
- Research plan: (1) nail the exact vehicle from the listing, (2) find private-party comps for that
  year/trim/mileage, (3) check known problems / maintenance due at this mileage, (4) price the
  deferred work. Prefer valuation guides and live comparable listings over forums.
- fair_value = what this specific car is worth in a private-party sale today, in dollars.
- hidden_costs = work the buyer will have to pay for soon (belts, tires, brakes, timing service,
  registration-blocking issues). Cost in dollars. Only include work the evidence supports.
- red_flags = negotiation leverage: missing service records, salvage/branded title, accident
  history, above-market asking, evasive listing language.
- sources MUST be URLs you actually fetched or that came back from a search. Never invent one.
- If searches keep coming back empty, still finish — use the listing itself, say so in reasoning,
  and set confidence "low".
- Budget: you get at most $MAX_STEPS tool calls. Call finish before you run out.
"""
# NOTE: $MAX_STEPS is substituted with str.replace, not str.format — the prompt is
# full of literal JSON braces and .format() would try to read them as fields.

_OBS_CAP = 4000


def _step_prompt(kind: str, payload: dict) -> str:
    return f"OBSERVATION ({kind}):\n{json.dumps(payload, default=str)[:_OBS_CAP]}"


def _extract_json(s: str) -> dict:
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in model response: {s[:200]!r}")
    return json.loads(m.group(0))


def _heuristic_payload(listing_text: str, link: str, asking: Optional[float]) -> dict:
    """Deterministic valuation used when there is no LLM (or it never finished).

    Deliberately conservative: ~11% under asking is the typical private-party gap
    between list and transaction price, which keeps the demo believable offline.
    """
    text = listing_text or ""
    if not asking:
        m = re.search(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{4,6})", text)
        asking = float(m.group(1).replace(",", "")) if m else 0.0
    ym = re.search(r"\b(19|20)\d{2}\b", text)
    mm = re.search(r"([\d,]{3,7})\s*(?:mi\b|miles|k miles)", text, re.I)
    miles = int(mm.group(1).replace(",", "")) if mm else None
    if miles and miles < 500:                      # "68k miles" style
        miles *= 1000
    flags: list[str] = []
    low = text.lower()
    if "salvage" in low or "rebuilt" in low or "branded" in low:
        flags.append("title may be branded (salvage/rebuilt wording in listing)")
    if "as is" in low or "as-is" in low:
        flags.append("sold as-is, no warranty")
    if "service record" not in low and "maintenance record" not in low:
        flags.append("no service records mentioned")
    return {
        "fair_value": round((asking or 0) * 0.89, 2),
        "hidden_costs": [],
        "red_flags": flags or ["listing detail is thin — verify condition in person"],
        "facts": {"year": int(ym.group(0)) if ym else None, "make": "", "model": "",
                  "trim": "", "miles": miles, "asking": asking or 0},
        "confidence": "low",
        "sources": [{"title": "listing", "url": link, "note": "listing page only — "
                                                              "no external comps gathered"}],
        "reasoning": ("Offline valuation: no research tools were available, so fair value is "
                      "an 11% haircut off asking (the typical private-party list-to-sale gap). "
                      "Treat this as a floor on confidence, not on price."),
        "steps": [{"tool": "fallback", "arg": link, "note": "heuristic valuation"}],
    }


def _normalize(payload: dict, link: str, asking: Optional[float],
               steps: list[dict]) -> dict:
    """Coerce a model payload into the contract, clamp nonsense, attach the trace."""
    facts = dict(payload.get("facts") or {})
    ask = float(facts.get("asking") or asking or 0) or 0.0
    facts["asking"] = ask

    fair = float(payload.get("fair_value") or 0)
    if ask and fair:                               # sanity clamp — never trust blindly
        fair = min(max(fair, 0.55 * ask), 1.05 * ask)

    costs = []
    for c in payload.get("hidden_costs") or []:
        try:
            costs.append({"item": str(c.get("item", "")).strip(),
                          "cost": float(c.get("cost") or 0)})
        except (AttributeError, TypeError, ValueError):
            continue
    costs = [c for c in costs if c["item"] and c["cost"] > 0]

    sources = []
    for s in payload.get("sources") or []:
        if isinstance(s, str):
            sources.append({"title": s, "url": s, "note": ""})
        elif isinstance(s, dict) and s.get("url"):
            sources.append({"title": str(s.get("title") or s["url"])[:160],
                            "url": str(s["url"]), "note": str(s.get("note") or "")[:240]})

    conf = str(payload.get("confidence") or "low").lower()
    if conf not in ("low", "med", "high"):
        conf = "low"
    if not sources and conf == "high":             # no citations, no high confidence
        conf = "med"

    return {
        "fair_value": round(fair, 2),
        "hidden_costs": costs,
        "red_flags": [str(f)[:200] for f in (payload.get("red_flags") or []) if str(f).strip()],
        "facts": facts,
        "confidence": conf,
        "sources": sources,
        "reasoning": str(payload.get("reasoning") or "")[:1200],
        "steps": steps,
        "listing_link": link,
    }


def run_research(link: str, *, asking: Optional[float] = None,
                 max_steps: Optional[int] = None,
                 on_step: Optional[Callable[[dict], None]] = None) -> dict:
    """Research one listing and return the valuation payload. Never raises.

    `on_step(step)` is called after every tool call with
    {"tool", "arg", "note", "thought"} so the dashboard can stream the trace live.
    """
    steps: list[dict] = []

    def record(tool: str, arg: str, note: str, thought: str = "") -> None:
        step = {"tool": tool, "arg": arg, "note": note, "thought": thought}
        steps.append(step)
        if on_step:
            try:
                on_step(step)
            except Exception:  # noqa: BLE001 — a bad callback can't break research
                pass

    if RESEARCH_MODE == "mock":
        payload = dict(MOCK_PAYLOAD)
        for s in payload["steps"]:
            record(s["tool"], s["arg"], s["note"])
        return _normalize(payload, link, asking or payload["facts"]["asking"], steps)

    # Step 0 — always read the listing itself.
    listing = fetch_page(link)
    record("fetch_page", link,
           listing["error"] or f"{len(listing['text'])} chars of listing text")
    listing_text = listing["text"]

    if not runware.available():
        payload = _heuristic_payload(listing_text, link, asking)
        payload["steps"] = steps + payload["steps"]
        return _normalize(payload, link, asking, payload["steps"])

    budget = max_steps or RESEARCH_MAX_STEPS
    messages = [
        {"role": "system", "content": _SYSTEM.replace("$MAX_STEPS", str(budget))},
        {"role": "user", "content":
            f"Listing URL: {link}\n"
            f"Buyer-reported asking price: {asking if asking else 'unknown'}\n\n"
            f"Listing page text (may be truncated or blocked):\n"
            f"{listing_text or '(the listing page could not be read: ' + str(listing['error']) + ')'}\n\n"
            f"Begin. Respond with ONLY the JSON for your next action."},
    ]

    for i in range(budget):
        try:
            raw = runware.text_inference(messages, max_tokens=1400)
            action = _extract_json(raw)
        except Exception as e:  # noqa: BLE001 — model hiccup: nudge once, then bail
            record("error", "", f"model call failed: {e}")
            messages.append({"role": "user",
                             "content": "That was not valid JSON. Respond with ONLY the JSON "
                                        "object for your next action."})
            continue

        messages.append({"role": "assistant", "content": raw})
        tool = str(action.get("tool") or "").strip()
        thought = str(action.get("thought") or "")[:200]

        if tool == "finish":
            record("finish", "", f"confidence {action.get('confidence')}", thought)
            return _normalize(action, link, asking, steps)

        if tool == "web_search":
            q = str(action.get("query") or "")
            res = web_search(q)
            note = res["error"] or f"{len(res['results'])} results"
            record("web_search", q, note, thought)
            messages.append({"role": "user", "content": _step_prompt("web_search", res)})
        elif tool == "fetch_page":
            url = str(action.get("url") or "")
            res = fetch_page(url)
            note = res["error"] or f"{len(res['text'])} chars"
            record("fetch_page", url, note, thought)
            messages.append({"role": "user", "content": _step_prompt("fetch_page", res)})
        else:
            record("error", tool, "unknown tool", thought)
            messages.append({"role": "user",
                             "content": 'Unknown tool. Use "web_search", "fetch_page", '
                                        'or "finish".'})

        left = budget - i - 1
        if left <= 1:
            messages.append({"role": "user",
                             "content": f"You have {left} tool call(s) left. Respond with the "
                                        f'"finish" JSON now.'})

    # Ran out of steps without finishing.
    record("timeout", "", f"no finish after {budget} steps")
    payload = _heuristic_payload(listing_text, link, asking)
    payload["reasoning"] = ("Research ran out of steps before converging; falling back to a "
                            "conservative haircut off asking. " + payload["reasoning"])
    return _normalize(payload, link, asking, steps + payload["steps"])


# ── Downstream contract (unchanged from the expert era) ──────────────────────
def to_valuation(payload: dict, asking: Optional[float] = None) -> dict:
    """Derive {asking, R, V} from a research payload."""
    facts = payload.get("facts") or {}
    asking = float(asking or facts.get("asking") or 0) or 0.0
    fair_value = float(payload.get("fair_value") or 0)
    hidden = sum(float(h.get("cost", 0)) for h in payload.get("hidden_costs", []))
    R = fair_value - hidden
    if asking:
        R = max(R, 0.65 * asking)                  # sanity floor
    return {"asking": asking, "V": fair_value, "R": round(R, 2)}


def research_summary(payload: dict) -> str:
    """Short iMessage summarizing what Closer found, with its receipts."""
    v = to_valuation(payload)
    facts = payload.get("facts") or {}
    car = " ".join(str(facts.get(k) or "") for k in ("year", "make", "model", "trim")).strip()
    car = car or "car"
    costs = payload.get("hidden_costs") or []
    cost_line = ", ".join(f"{c['item']} (${int(c['cost']):,})" for c in costs) or "none found"
    flags = "; ".join(payload.get("red_flags") or []) or "none"
    n = len([s for s in payload.get("steps", []) if s.get("tool") in ("web_search", "fetch_page")])
    srcs = payload.get("sources") or []
    src_line = ""
    if srcs:
        src_line = "\nSources: " + ", ".join(
            urllib.parse.urlparse(s["url"]).netloc.replace("www.", "")
            for s in srcs[:3] if s.get("url"))
    return (
        f"Did my homework on the {car}. 🔎 ({n} sources checked, "
        f"{payload.get('confidence', 'low')} confidence)\n"
        f"Fair value ~${int(v['V']):,}. Hidden costs: {cost_line}. "
        f"Red flags: {flags}.\n"
        f"Your walk-away is ${int(v['R']):,} — I'll defend it. "
        f"Relay each seller reply here (text or screenshot) and I'll tell you the exact move."
        f"{src_line}"
    )


# ── smoke test: python -m app.research <listing-url> ─────────────────────────
if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com/2019-mazda-cx-5"
    print(f"mode={RESEARCH_MODE} runware={'yes' if runware.available() else 'no'} "
          f"search={SEARCH_PROVIDER}\n")
    out = run_research(url, on_step=lambda s: print(
        f"  [{s['tool']}] {s['arg'][:70]!r} -> {s['note']}"))
    print("\n" + json.dumps(out, indent=2)[:2500])
    print("\nvaluation:", to_valuation(out))
    print("\n" + research_summary(out))
