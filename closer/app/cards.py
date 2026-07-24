"""Unicode cards and every line of user-facing copy — update_1.md §4.6, §7 B2/B3.

Ships before `app/render.py` (the matplotlib PNG cards) because it has zero
unknowns — the demo is never blocked on a chart. The PNG card is an upgrade that
lands on top of this, same data, same call sites.

━━ Typography rule — the one that breaks the demo if ignored ━━━━━━━━━━━━━━━━━
iMessage renders a proportional font. **Never build columns with spaces.** They
will not align on the recipient's device and the demo will look broken on
someone else's phone. Three things render identically across every iOS version:

    label: value          on its own line
    ▁▂▃▄▅▆▇█              block-element sparklines
    ●●●●○                 filled/empty dot meters

Use those. Nothing else. The three-space indent on continuation lines is not a
column — nothing below it has to line up with anything above it — so it survives
a proportional font. Any layout that *does* require two lines to align is banned.

No markdown either: iMessage renders none of it, so `**bold**` arrives as
literal asterisks (§5.7). Emoji are the only formatting that exists.

━━ Where the numbers come from ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`Deal.trajectory()` (§4.4, Lane A) is a derivation over `feed` — every closer
turn already carries the full `recommend()` dict, so the cards need zero new
persistence. Lane B must not block on Lane A landing it, so `_trajectory()`
below calls the method when it exists and derives the identical list when it
does not. Same for `nickname` and `closed_price` (§4.3): read defensively,
fall back to the value `main.py` computes inline today.

━━ Savings math is frozen (§4.5) — one formula, used everywhere ━━━━━━━━━━━━━━
    closed:  saved     = asking - closed_price
    walked:  avoided   = max(0, last_seller_price - V)
    open:    projected = asking - snapshot.offer

`avoided` is real but never sums into the headline "saved" number — it gets its
own line, phrased honestly. `projected` is never called "saved".
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:                                  # avoid an import cycle at runtime
    from .state import Deal

# Sparkline ramp and meter glyphs, shared so every card looks like one product.
BLOCKS = "▁▂▃▄▅▆▇█"
DOT_FULL, DOT_EMPTY = "●", "○"
IND = "   "                                        # continuation indent, not a column

# A "bluff called by math" is the conjunction of two facts about one turn:
# the seller applied pressure, and the posterior did not care. Under 1% of the
# asking price is the threshold from §4.6.
BLUFF_MOVE_FRACTION = 0.01

# Longest a deal can contribute to the "minutes texting me" line. A deal left
# open over a weekend did not cost the user a weekend of texting; without a cap
# the stats card's best line becomes a lie.
_MAX_MINUTES_PER_DEAL = 30.0


# ── field access that works on both sides of the Lane A merge ────────────────
def _name(deal: "Deal") -> str:
    """Nickname wins over title (§4.3). `nickname` is a Lane A addition to the
    Deal model, so read it defensively until that lands."""
    return (getattr(deal, "nickname", None) or deal.title or "This deal").strip()


def _money(n: Optional[float]) -> str:
    return f"${n:,.0f}" if n is not None else "—"


def _state(deal: "Deal") -> str:
    return getattr(deal.state, "value", str(deal.state))


def _snapshot(deal: "Deal") -> dict:
    return deal.snapshot or {}


def _closed_price(deal: "Deal") -> Optional[float]:
    """What the user actually paid.

    `closed_price` is frozen at the moment of close (§4.3) precisely because a
    later UNDO can change the log it would otherwise be recomputed from. Until
    Lane A adds the field, fall back to the exact expression `main.py:237` uses
    to print the close message — the same number, just not yet persisted.
    """
    price = getattr(deal, "closed_price", None)
    if price is not None:
        return float(price)
    return deal.last_user_offer or deal.last_seller_price


def _trajectory(deal: "Deal") -> list[dict]:
    """Per-turn belief history. `Deal.trajectory()` when Lane A has landed it,
    an identical derivation over `feed` when it has not (§4.4)."""
    fn = getattr(deal, "trajectory", None)
    if callable(fn):
        try:
            return list(fn())
        except Exception:                          # pragma: no cover - defensive
            pass
    out: list[dict] = []
    for i, t in enumerate(deal.feed):
        rec = t.recommendation
        if not rec:
            continue
        prev = deal.feed[i - 1] if i else None
        out.append({
            "turn": len(out) + 1,
            "ts": t.ts,
            "floor_est": rec.get("floor_point_est"),
            "floor_std": rec.get("floor_std"),
            "seller_price": rec.get("last_seller_price"),
            "our_offer": rec.get("offer"),
            "p_accept": rec.get("p_accept"),
            "action": rec.get("action"),
            "signals": (prev.signals if prev else None),
            "seller_text": (prev.text if prev else None),
        })
    return out


# ── the three shared glyph helpers ───────────────────────────────────────────
def sparkline(values: Sequence[Optional[float]]) -> str:
    """One block per value, scaled across the series' own min/max.

    Two equal values must produce the same glyph — that is the entire point on
    the bluff turn, where the floor did not move and the picture has to show it.
    A flat series renders as a flat mid-height line rather than dividing by zero.
    """
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    if hi - lo < 1e-9:
        return BLOCKS[len(BLOCKS) // 2] * len(nums)
    span = hi - lo
    return "".join(BLOCKS[min(len(BLOCKS) - 1, int((v - lo) / span * len(BLOCKS)))]
                   for v in nums)


def meter(filled: int, total: int = 5) -> str:
    filled = max(0, min(total, filled))
    return DOT_FULL * filled + DOT_EMPTY * (total - filled)


def confidence_dots(floor_std: Optional[float], asking: Optional[float]) -> int:
    """How tight the posterior is, as a 0–5 meter.

    Scaled by the asking price so it means the same thing on a $6k Camry and a
    $40k truck: a ±$300 spread is tight on one and noise on the other.
    """
    if floor_std is None or not asking:
        return 0
    ratio = float(floor_std) / float(asking)
    for threshold, dots in ((0.015, 5), (0.03, 4), (0.05, 3), (0.08, 2)):
        if ratio <= threshold:
            return dots
    return 1


# ── the deal card ────────────────────────────────────────────────────────────
_ACTION_LINE = {
    "COUNTER": ("👉", "Send"),
    "ACCEPT": ("✅", "Take it at"),
    "HOLD": ("✋", "Hold at"),
    "WALK": ("🚶", "Walk. Their floor is above"),
}


# The user relays in third person — "he says three other people are coming".
# Strip the reporting verb so the card quotes the claim, not the relay.
_RELAY_PREAMBLE = re.compile(
    r"^(?:and\s+)?(?:he|she|they|the seller|seller|dude|guy)\s+"
    r"(?:just\s+)?(?:says?|said|is saying|claims?|claimed|goes|wrote|texted|replied)"
    r"(?:\s+that)?[,:]?\s+", re.IGNORECASE)


def _quote(text: Optional[str], limit: int = 58) -> Optional[str]:
    """The seller's own words, trimmed to a phrase at a word boundary.

    Generated from the feed, never templated — if there is nothing to quote the
    caller drops the line rather than inventing one.
    """
    if not text:
        return None
    t = " ".join(text.split()).strip(" .!?\"'")
    t = _RELAY_PREAMBLE.sub("", t).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0]
    return (cut or t[:limit]).rstrip(" ,;:-") + "…"


def _bluff_block(deal: "Deal", traj: list[dict]) -> list[str]:
    """The whole pitch in four lines. §4.6.

    Emitted only when a turn had `bluff_claim=True` AND that turn's `floor_est`
    delta was under 1% of `asking`. That conjunction is the product: pressure
    applied, math unmoved. If no turn qualifies, the block is dropped — never
    faked, never softened into "possibly a bluff".

    Turn 1 can never qualify: there is no prior estimate to have failed to move.
    The most recent qualifying turn wins, because that is the one still in the
    user's head.
    """
    asking = deal.asking
    if not asking or len(traj) < 2:
        return []
    limit = BLUFF_MOVE_FRACTION * float(asking)
    for cur, prev in zip(reversed(traj[1:]), reversed(traj[:-1])):
        sig = cur.get("signals") or {}
        if not sig.get("bluff_claim"):
            continue
        a, b = cur.get("floor_est"), prev.get("floor_est")
        if a is None or b is None:
            continue
        delta = abs(float(a) - float(b))
        if delta >= limit:
            continue                               # they moved: it was not cheap talk
        lines = [""]
        quote = _quote(cur.get("seller_text"))
        head = f"🎣 Turn {cur['turn']}"
        lines.append(f'{head} — "{quote}"' if quote else f"{head} — the pressure play.")
        moved = "didn't move at all" if delta < 1 else f"moved {_money(delta)}"
        lines.append(f"{IND}The curve {moved}. That was a bluff.")
        return lines
    return []


def deal_card(deal: "Deal") -> str:
    """The money artifact — where the seller's floor estimate is, where it
    started, and the turn where it refused to move.

        🚗 2008 Toyota Camry LE — turn 4 of a live deal
        Listed $6,400 · they're at $5,400

        Their floor now reads $5,062
        Turn 1 it read $5,601 — down $539
        █▄▄▁  turn 1 → 4

        Confidence ●●●●○ (±$188)
        Zone of agreement $4,796–$5,200

        ✋ Hold at $4,992
           41% they take it

        🎣 Turn 3 — "He says three other people are coming to see it…"
           The curve moved $4. That was a bluff.

    Degrades all the way down: a deal with no research, no snapshot and no turns
    still returns something a human can read, because that is what a judge sees
    in the first thirty seconds.
    """
    state = _state(deal)
    traj = _trajectory(deal)
    snap = _snapshot(deal)

    # ── header ───────────────────────────────────────────────────────────────
    if state == "AWAITING_LINK":
        return "\n".join([
            f"🚗 {_name(deal)}",
            "",
            "Nothing to show yet — I don't have the listing.",
            "Send me the link and I'll come back with what it's actually worth.",
        ])

    if state == "AWAITING_RESEARCH":
        lines = [f"🔎 {_name(deal)} — researching"]
        if deal.asking is not None:
            lines.append(f"Listed {_money(deal.asking)}")
        lines.append("")
        steps = [s for s in (deal.research_steps or []) if s.get("note")]
        if steps:
            for s in steps[-3:]:
                lines.append(f"{IND}{s['note']}")
            lines.append("")
        lines.append("Comps and known problems, then a number. ~30s.")
        return "\n".join(lines)

    turns = len(traj)
    if state == "CLOSED":
        head = f"🤝 {_name(deal)} — closed"
    elif state == "WALKED":
        head = f"🚶 {_name(deal)} — walked"
    elif turns:
        head = f"🚗 {_name(deal)} — turn {turns} of a live deal"
    else:
        head = f"🚗 {_name(deal)} — ready when they are"
    lines = [head]

    if deal.asking is not None:
        sub = f"Listed {_money(deal.asking)}"
        # Where they stood matters while it's live and at the moment you walked.
        # On a closed deal it's noise — what you paid is the only number left.
        if deal.last_seller_price is not None and state != "CLOSED":
            sub += f" · they're at {_money(deal.last_seller_price)}"
        lines.append(sub)

    # ── outcome cards stop here: the number that matters is what you paid ────
    if state == "CLOSED":
        price = _closed_price(deal)
        lines += ["", f"You paid {_money(price)}"]
        saved = _saved(deal)
        if saved:
            pct = saved / float(deal.asking) if deal.asking else 0
            lines.append(f"{IND}{_money(saved)} under ask ({pct:.0%})")
        return "\n".join(lines)

    if state == "WALKED":
        lines += ["", "You walked."]
        avoided = _avoided(deal)
        if avoided:
            lines.append(f"{IND}They never came under fair value — "
                         f"{_money(avoided)} over, at the end.")
        elif deal.V is not None:
            lines.append(f"{IND}Fair value was {_money(deal.V)}.")
        return "\n".join(lines)

    # ── the belief curve ─────────────────────────────────────────────────────
    if not traj:
        lines += ["", "No turns yet — I'm holding the research."]
        if deal.V is not None:
            lines.append(f"Fair value reads {_money(deal.V)}.")
        lines.append("Relay whatever they say next and I'll price the reply.")
        return "\n".join(lines)

    floors = [t.get("floor_est") for t in traj]
    now, first = floors[-1], floors[0]
    lines.append("")
    if now is not None:
        lines.append(f"Their floor now reads {_money(now)}")
    if first is not None and now is not None and len(traj) > 1:
        delta = now - first
        if abs(delta) < 1:
            lines.append(f"Turn 1 it read {_money(first)} — unchanged")
        else:
            way = "down" if delta < 0 else "up"
            lines.append(f"Turn 1 it read {_money(first)} — {way} {_money(abs(delta))}")
    spark = sparkline(floors)
    if spark and len(traj) > 1:
        lines.append(f"{spark}  turn 1 → {turns}")

    # ── how sure, and where a deal could live ────────────────────────────────
    std = snap.get("floor_std") if snap else traj[-1].get("floor_std")
    dots = confidence_dots(std, deal.asking)
    meta: list[str] = []
    if dots:
        meta.append(f"Confidence {meter(dots)} (±{_money(std)})")
    low, ceiling = snap.get("zopa_low"), snap.get("ceiling")
    if low is not None and ceiling is not None:
        if low <= ceiling:
            meta.append(f"Zone of agreement {_money(low)}–{_money(ceiling)}")
        else:
            meta.append(f"No zone of agreement — their floor reads above "
                        f"your {_money(ceiling)} ceiling")
    if meta:
        lines += [""] + meta

    # ── the number, in its own bubble-worthy block (§5.7) ────────────────────
    action = (snap.get("action") or traj[-1].get("action") or "").upper()
    offer = snap.get("offer", traj[-1].get("our_offer"))
    icon, verb = _ACTION_LINE.get(action, ("👉", "Send"))
    if offer is not None:
        lines += ["", f"{icon} {verb} {_money(offer)}"]
        p = snap.get("p_accept", traj[-1].get("p_accept"))
        if action == "WALK":
            p_close = snap.get("p_close")
            if p_close is not None:
                lines.append(f"{IND}only {p_close:.0%} chance a deal exists there")
        elif p is not None:
            lines.append(f"{IND}{p:.0%} they take it")

    lines += _bluff_block(deal, traj)
    return "\n".join(lines)


# ── the deal list ────────────────────────────────────────────────────────────
def _list_detail(deal: "Deal") -> Optional[str]:
    """Second line of a list row: the one fact that distinguishes this deal."""
    state = _state(deal)
    if state == "CLOSED":
        saved = _saved(deal)
        paid = _closed_price(deal)
        if saved:
            return f"saved {_money(saved)}"
        return f"paid {_money(paid)}" if paid is not None else None
    if state == "WALKED":
        avoided = _avoided(deal)
        return (f"walked — {_money(avoided)} over fair value" if avoided
                else "walked away")
    if state == "AWAITING_LINK":
        return "waiting on a link"
    if deal.asking is None:
        return None
    line = f"{_money(deal.asking)} ask"
    snap = _snapshot(deal)
    offer = snap.get("offer")
    if offer is not None:
        action = (snap.get("action") or "").upper()
        verb = {"HOLD": "hold at", "WALK": "walk from", "ACCEPT": "take"}.get(action, "send")
        line += f" · {verb} {_money(offer)} next"
    return line


def _switch_example(deals: Sequence["Deal"], focus_id: Optional[str]) -> str:
    """The word to put in the "switch to the ___" hint.

    Has to be a word that actually resolves through `intent.resolve_switch`, so
    it is a real token from a real title — the last alphabetic word of four or
    more characters, which lands on the model ("Camry", "Civic") rather than the
    year or the trim. Prefers a deal the user is NOT already on, because a hint
    that switches to where you already are teaches nothing.
    """
    pool = [d for d in deals if not focus_id or d.id != focus_id] or list(deals)
    for deal in pool:
        words = [w.strip("-—·,.") for w in _name(deal).split()]
        good = [w for w in words if len(w) >= 4 and w.isalpha()]
        if good:
            return good[-1]
    return "Civic"


def deal_list(deals: Sequence["Deal"], focus_id: Optional[str] = None) -> str:
    """Numbered deal list. `▶` marks focus.

        📋 Your deals

        ▶ 1. 2008 Toyota Camry LE — negotiating, turn 4
             $6,400 ask · hold at $4,992 next
          2. 2016 Honda Civic EX — researching…
             $11,900 ask

        Reply with a number to switch, or say "switch to the Civic".

    The caller MUST set `last_card_kind = "list"` and cache this ordering in the
    user meta, so a bare-integer reply resolves against exactly what the user
    saw (§4.1, the SWITCH guard). `intent.resolve_switch` expects the same
    ordering for its index tier.
    """
    if not deals:
        return no_deals()

    label = {
        "AWAITING_LINK": "waiting on a link",
        "AWAITING_RESEARCH": "researching…",
        "NEGOTIATING": "negotiating",
        "CLOSED": "closed 🤝",
        "WALKED": "walked 🚶",
    }
    out = ["📋 Your deals", ""]
    for i, d in enumerate(deals, 1):
        mark = "▶" if (focus_id and d.id == focus_id) else " "
        state = label.get(_state(d), _state(d).lower())
        turns = len(_trajectory(d))
        if _state(d) == "NEGOTIATING" and turns:
            state += f", turn {turns}"
        out.append(f"{mark} {i}. {_name(d)} — {state}")
        detail = _list_detail(d)
        # A row whose detail just restates its state label is a wasted line.
        if detail and detail not in state:
            out.append(f"{IND}{IND}{detail}")

    out += ["", f'Reply with a number to switch, or say "switch to the '
                f'{_switch_example(deals, focus_id)}".']
    return "\n".join(out)


# ── savings math, §4.5, one definition ───────────────────────────────────────
def _saved(deal: "Deal") -> Optional[float]:
    """closed: asking - closed_price. None unless the deal actually closed."""
    if _state(deal) != "CLOSED":
        return None
    price = _closed_price(deal)
    if price is None or deal.asking is None:
        return None
    return max(0.0, float(deal.asking) - float(price))


def _avoided(deal: "Deal") -> Optional[float]:
    """walked: max(0, last_seller_price - V). Never summed into "saved"."""
    if _state(deal) != "WALKED":
        return None
    if deal.last_seller_price is None or deal.V is None:
        return None
    return max(0.0, float(deal.last_seller_price) - float(deal.V))


def _projected(deal: "Deal") -> Optional[float]:
    """open: asking - snapshot.offer. Never called "saved"."""
    offer = _snapshot(deal).get("offer")
    if offer is None or deal.asking is None:
        return None
    return max(0.0, float(deal.asking) - float(offer))


def _minutes(deals: Sequence["Deal"]) -> float:
    """Thread time, per deal, capped — see `_MAX_MINUTES_PER_DEAL`."""
    total = 0.0
    for d in deals:
        span = (float(d.updated_at) - float(d.created_at)) / 60.0
        total += min(max(span, 0.0), _MAX_MINUTES_PER_DEAL)
    return total


def stats_card(deals: Sequence["Deal"]) -> str:
    """Lifetime stats.

        📊 Closer, all time

        💰 $1,500 saved across 1 closed deal
           10% under ask

        🏆 Best: 2014 Ford F-150 XLT
           $1,500 under ask (10%)

        🚶 Walked once — $800 over fair value
        📈 5 deals total · 2 live · 4 turns to close

        You've spent about 9 minutes texting me.

    That last line is deliberate: "nine minutes for $1,500" is the value
    proposition stated as a fact about the user's own data.
    """
    deals = list(deals)
    if not deals:
        return "\n".join([
            "📊 Closer, all time",
            "",
            "Nothing yet — no deals, no savings, no receipts.",
            "Send me a listing link and let's put a number on the board.",
        ])

    closed = [d for d in deals if _state(d) == "CLOSED"]
    walked = [d for d in deals if _state(d) == "WALKED"]
    live = [d for d in deals if d.is_active()]

    lines = ["📊 Closer, all time", ""]

    saved_pairs = [(d, s) for d in closed if (s := _saved(d)) is not None]
    total_saved = sum(s for _, s in saved_pairs)
    if total_saved > 0:
        n = len(saved_pairs)
        lines.append(f"💰 {_money(total_saved)} saved across {n} closed "
                     f"{'deal' if n == 1 else 'deals'}")
        pcts = [s / float(d.asking) for d, s in saved_pairs if d.asking]
        if pcts:
            avg = sum(pcts) / len(pcts)
            tail = "under ask" if n == 1 else "under ask on average"
            lines.append(f"{IND}{avg:.0%} {tail}")
    elif closed:
        lines.append(f"🤝 {len(closed)} closed, none of them under ask")
    else:
        # Nothing closed yet — lead with what's on the table, honestly labelled.
        proj = [p for d in live if (p := _projected(d)) is not None]
        if proj:
            lines.append(f"🎯 {_money(sum(proj))} on the table across "
                         f"{len(proj)} live {'deal' if len(proj) == 1 else 'deals'}")
            lines.append(f"{IND}projected, not banked — nothing's closed yet")
        else:
            lines.append("🎯 Nothing closed yet. The board is still open.")

    if len(saved_pairs) > 1:
        best, best_saved = max(saved_pairs, key=lambda p: p[1])
        pct = best_saved / float(best.asking) if best.asking else 0
        lines += ["", f"🏆 Best: {_name(best)}", f"{IND}{_money(best_saved)} under ask ({pct:.0%})"]

    tail: list[str] = []
    if walked:
        worst = max((a for d in walked if (a := _avoided(d)) is not None), default=0.0)
        word = "once" if len(walked) == 1 else f"{len(walked)} times"
        tail.append(f"🚶 Walked {word}" + (f" — {_money(worst)} over fair value"
                                           if worst else ""))

    counts = [f"{len(deals)} deal{'' if len(deals) == 1 else 's'} total"]
    if live:
        counts.append(f"{len(live)} live")
    turn_counts = [len(_trajectory(d)) for d in closed]
    turn_counts = [t for t in turn_counts if t]
    if turn_counts:
        avg_turns = sum(turn_counts) / len(turn_counts)
        counts.append(f"{avg_turns:.0f} turns to close"
                      + ("" if len(turn_counts) == 1 else " on average"))
    tail.append("📈 " + " · ".join(counts))
    lines += [""] + tail

    mins = _minutes(deals)
    if mins >= 1:
        lines += ["", f"You've spent about {mins:.0f} minutes texting me."]
    return "\n".join(lines)


# ── copy (§7 B3) ─────────────────────────────────────────────────────────────
# Voice: a sharp friend who has done this a hundred times. Short. Specific
# numbers, never ranges. Never apologise. Never say "I'm an AI".

def onboarding() -> str:
    """First message to a phone number that has never texted us. No signup, no
    login — the phone number IS the account (§3), so this is the entire
    onboarding surface."""
    return "\n".join([
        "I'm Closer. Send me a used-car listing and I'll tell you what it's "
        "actually worth, then coach every counter until you're done.",
        "",
        'Text me a link to start. Say "help" for the rest.',
    ])


def help_card() -> str:
    """Capability card — the §4.1 table in the user's language: what to say,
    not what the intent is called."""
    return "\n".join([
        "🤝 Closer",
        "",
        "Send a listing link and I'll research the car, then price every counter.",
        "",
        # One paragraph per bubble line: iMessage wraps proportional text itself,
        # and a hard break mid-sentence lands in a different place on every phone.
        "Relay whatever the seller says — typed, pasted, or a screenshot of your chat "
        "with them. I read the price out and tell you the number to send back.",
        "",
        'Say "card" for where this one stands.',
        'Say "deals" to see all of them, then reply with a number to switch.',
        'Say "stats" for everything you\'ve saved.',
        'Say "undo" if you relayed something wrong.',
        'Say "we have a deal" when you close, or "I walked" when you don\'t.',
        "",
        'Rename one with "call this the red Civic". Drop one with "delete the Civic".',
    ])


def no_deals() -> str:
    return "\n".join([
        "📋 No deals yet.",
        "",
        "Send me a listing link and I'll start one.",
    ])


def deal_parked(new_deal: "Deal", parked: "Deal") -> str:
    """A second link arrives while a deal is live. A new link NEVER reuses an
    existing deal (§7 A2) — it creates one and moves focus, and the reply names
    what got parked so the user is never surprised about which deal they're on.
    """
    return "\n".join([
        f"On it — researching the {_name(new_deal)} now. 🔎",
        "",
        f"{_name(parked)} is parked, not lost. Say \"deals\" to switch back.",
    ])


def switched(deal: "Deal") -> str:
    return f"↩️ Back on the {_name(deal)}."


def ambiguous_switch(arg: str, candidates: Sequence["Deal"]) -> str:
    """Two deals match. Ask — never guess (§4.1). The numbering here is a LIST
    for switching purposes, so the caller sets `last_card_kind = "list"` and
    caches this ordering exactly as it would for `deal_list`."""
    lines = [f'"{arg}" matches {len(candidates)} of them:', ""]
    for i, d in enumerate(candidates, 1):
        lines.append(f"  {i}. {_name(d)}")
    lines += ["", "Which one? Reply with the number."]
    return "\n".join(lines)


def no_match(arg: str) -> str:
    return "\n".join([
        f'Nothing here called "{arg}".',
        'Say "deals" and I\'ll show you what you\'ve got.',
    ])


def confirm_delete(deal: "Deal") -> str:
    return "\n".join([
        f"Delete the {_name(deal)}? That takes its history with it.",
        'Reply "yes" and it\'s gone.',
    ])


def deleted(name: str) -> str:
    return f"Gone. The {name} is off your board."


def renamed(deal: "Deal") -> str:
    return f'Got it — this one\'s "{_name(deal)}" from here on.'


def undone(deal: "Deal") -> str:
    """UNDO pops the last seller turn and replays (§4.1). Say what came back."""
    snap = _snapshot(deal)
    offer = snap.get("offer")
    turns = len(_trajectory(deal))
    if offer is None:
        return "Pulled that turn back. Clean slate on this one — relay it again."
    action = (snap.get("action") or "").upper()
    verb = {"HOLD": "Hold at", "WALK": "Walk from", "ACCEPT": "Take it at"}.get(action, "Send")
    return "\n".join([
        f"Pulled that one back — we're at turn {turns} again.",
        "",
        f"{verb} {_money(offer)}. Relay what they actually said.",
    ])


def deal_limit(limit: int) -> str:
    """§3 abuse limits. There is no signup gate, so this is the only gate."""
    return "\n".join([
        f"You've got {limit} running — that's my ceiling.",
        'Close or walk one first, or say "delete the Civic" to drop it.',
    ])


def throttled() -> str:
    return "Easy — that's a lot at once. Give me a minute and send it again."


def research_blocked(deal: "Deal") -> str:
    """§7 A4: the listing 403'd and nothing parsed. Ask for the one number that
    unblocks everything rather than emitting a $0 valuation."""
    site = "The listing site"
    if deal.listing_link:
        try:
            host = deal.listing_link.split("//", 1)[-1].split("/", 1)[0]
            site = host.replace("www.", "") or site
        except Exception:                          # pragma: no cover - defensive
            pass
    return "\n".join([
        f"{site} blocked me — I can't read the listing.",
        "",
        "What are they asking? Send me the number and I'll work from comps.",
    ])


def research_started(link: str) -> str:
    del link                                       # the user just sent it; don't echo
    return "On it — pulling comps and known problems for this one. ~30s. 🔎"


def no_focus() -> str:
    return "\n".join([
        "No deal in focus.",
        'Send a listing link to start one, or say "deals" to pick one up.',
    ])


def not_negotiating(deal: "Deal") -> str:
    """A relay arrived on a deal that isn't taking turns."""
    state = _state(deal)
    if state == "AWAITING_RESEARCH":
        return "Still digging into comps — one sec."
    if state in ("CLOSED", "WALKED"):
        return "\n".join([
            f"The {_name(deal)} is wrapped.",
            'Send a new listing link to start another, or say "deals" to switch.',
        ])
    return "Send me the listing link first and I'll price this properly."


def unparsed() -> str:
    return ("Didn't catch a seller message in that — paste their text, "
            "or a screenshot of your chat with them.")


def closed_message(deal: "Deal") -> str:
    """Close confirmation. `closed_price` is frozen at this moment (§4.3)."""
    price = _closed_price(deal)
    saved = _saved(deal)
    head = f"🤝 Closed at {_money(price)}"
    if saved:
        head += f" — {_money(saved)} under ask"
    return "\n".join([head + ".", "", "Nice work. That's on your stats now."])


def walked_message(deal: "Deal") -> str:
    avoided = _avoided(deal)
    lines = ["🚶 Logged as walked."]
    if avoided:
        lines.append(f"{_money(avoided)} over fair value at the end — "
                     "better than owning that.")
    else:
        lines.append("Better than overpaying.")
    lines += ["", "Text a new listing link whenever you want to run another."]
    return "\n".join(lines)


def error() -> str:
    """Never apologise, never explain the stack trace."""
    return "Something went sideways on my end. Send that again."


__all__ = [
    # cards
    "deal_card", "deal_list", "stats_card", "help_card", "onboarding",
    # copy
    "no_deals", "deal_parked", "switched", "ambiguous_switch", "no_match",
    "confirm_delete", "deleted", "renamed", "undone", "deal_limit", "throttled",
    "research_blocked", "research_started", "no_focus", "not_negotiating",
    "unparsed", "closed_message", "walked_message", "error",
    # glyphs + helpers
    "BLOCKS", "DOT_FULL", "DOT_EMPTY", "sparkline", "meter", "confidence_dots",
]


# ── python -m app.cards --demo ───────────────────────────────────────────────
def _demo_deals() -> list["Deal"]:
    """Load the committed fixtures (`tests/fixtures/*.json`), newest first.

    Falls back to a synthesised pair if the fixtures aren't on disk, so `--demo`
    works from a bare checkout. Reaching into `tests/` from `app/` is confined
    to this `__main__` helper and never imported by the app.
    """
    import json
    from pathlib import Path

    from .state import Deal, DealState

    here = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    names = ["deal_camry.json", "deal_civic.json", "deal_f150.json",
             "deal_tacoma.json", "deal_fresh.json"]
    loaded = [Deal(**json.loads((here / n).read_text()))
              for n in names if (here / n).exists()]
    if loaded:
        return loaded
    return [
        Deal(user_id="phone:+12055550100", title="2008 Toyota Camry LE",
             asking=6400.0, R=4160.0, V=5200.0, last_seller_price=5400.0,
             state=DealState.NEGOTIATING),
        Deal(user_id="phone:+12055550100", title="2016 Honda Civic EX",
             asking=11_900.0, state=DealState.AWAITING_RESEARCH),
    ]


def _demo_renderings() -> list[tuple[str, str]]:
    deals = _demo_deals()
    out = [(f"deal_card · {_state(d)}", deal_card(d)) for d in deals]
    out += [
        ("deal_list", deal_list(deals, deals[0].id)),
        ("deal_list · empty", deal_list([], None)),
        ("stats_card", stats_card(deals)),
        ("stats_card · empty", stats_card([])),
        ("help_card", help_card()),
        ("onboarding", onboarding()),
    ]
    return out


if __name__ == "__main__":                          # pragma: no cover
    import sys
    import time

    args = sys.argv[1:]
    if "--demo" not in args:
        print("usage: python -m app.cards --demo [--send +1XXXXXXXXXX]\n"
              "\n"
              "  --demo   print every card, including the null states\n"
              "  --send   also text them to a number, so the §4.6 typography\n"
              "           rule can be checked on a real phone rather than in a\n"
              "           terminal that renders a monospace font and lies")
        raise SystemExit(2)

    rule = "─" * 46
    renderings = _demo_renderings()
    for title, body in renderings:
        print(f"\n{rule}\n{title}\n{rule}\n{body}")
    print()

    if "--send" in args:
        to = args[args.index("--send") + 1]
        from . import linq
        if not linq.available():
            raise SystemExit("LINQ_API_KEY is not set — nothing to send with.")
        for title, body in renderings:
            linq.send(to, body)
            print(f"sent {title} → {to}")
            time.sleep(0.6)     # §5.7: bubbles under ~400ms apart arrive out of order
