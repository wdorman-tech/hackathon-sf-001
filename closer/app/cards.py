"""Unicode cards — the rendering contract from update_1.md §4.6.

STUB. Lane B (`lane/agent`) owns this file. Committed to main ahead of the lanes
so `main.py` and the demo scripts can import the frozen names immediately.

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

Use those. Nothing else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:                                  # avoid an import cycle at runtime
    from .state import Deal

# Sparkline ramp and meter glyphs, shared so every card looks like one product.
BLOCKS = "▁▂▃▄▅▆▇█"
DOT_FULL, DOT_EMPTY = "●", "○"


def _name(deal: "Deal") -> str:
    """Nickname wins over title (§4.3). `nickname` is a Lane A addition to the
    Deal model, so read it defensively until that lands."""
    return getattr(deal, "nickname", None) or deal.title


def _money(n: Optional[float]) -> str:
    return f"${n:,.0f}" if n is not None else "—"


def deal_card(deal: "Deal") -> str:
    """The money artifact. Target layout (§4.6):

        🚗 2008 Camry LE — turn 4 of a live deal
        Listed $6,400 · they're at $5,400

        Their floor now reads $4,910
        Turn 1 it read $6,180 — down $1,270
        ▇▇▆▅▄▃  turn 1 → 4

        Confidence ●●●●○ (±$310)
        Zone of agreement $4,600–$5,200

        👉 Send $4,750
           68% they take it

        🎣 Turn 3 — "three people coming Saturday."
           The curve moved $9. That was a bluff.

    The last block is the entire pitch in four lines and it must be GENERATED,
    not templated. Emit it when a turn had `bluff_claim=True` **and** that turn's
    `floor_est` delta was under 1% of `asking`. That conjunction is the product.
    If no turn qualifies, drop the block — never fake it.

    Data source is `deal.trajectory()` (Lane A adds it to state.py); every
    closer turn in `feed` already carries the full `recommend()` dict, so the
    card needs zero new persistence.

    STUB — returns the header lines only.
    """
    lines = [f"🚗 {_name(deal)}"]
    if deal.asking is not None:
        head = f"Listed {_money(deal.asking)}"
        if deal.last_seller_price is not None:
            head += f" · they're at {_money(deal.last_seller_price)}"
        lines.append(head)
    # TODO(Lane B): floor-now / floor-then / sparkline / confidence meter /
    # ZOPA / recommendation / bluff callout, from deal.trajectory().
    return "\n".join(lines)


def deal_list(deals: list["Deal"], focus_id: Optional[str]) -> str:
    """Numbered deal list. `▶` marks focus. Target layout (§4.6):

        📋 Your deals

        ▶ 1. 2008 Camry LE — negotiating, turn 4
             $6,400 ask · send $4,750 next
          2. 2016 Civic EX — researching…
             $11,900 ask
          3. 2014 F-150 XLT — closed 🤝
             saved $2,100

        Reply with a number to switch, or say "switch to the Civic".

    The caller MUST set `last_card_kind = "list"` and cache this ordering in the
    user meta, so a bare-integer reply resolves against exactly what the user
    saw (§4.1, the SWITCH guard).

    STUB — numbering and focus marker only.
    """
    if not deals:
        return "📋 No deals yet. Send me a listing link to start one."
    out = ["📋 Your deals", ""]
    for i, d in enumerate(deals, 1):
        mark = "▶" if d.id == focus_id else " "
        out.append(f"{mark} {i}. {_name(d)} — {d.state.value.lower()}")
        # TODO(Lane B): the second line — ask, next offer, or outcome + savings.
    out += ["", 'Reply with a number to switch, or say "switch to the Civic".']
    return "\n".join(out)


def stats_card(deals: list["Deal"]) -> str:
    """Lifetime stats. Target layout (§4.6):

        📊 Closer, all time

        💰 $3,940 saved across 2 closed deals
           14% under ask on average

        🏆 Best: 2014 F-150 XLT
           $2,100 under ask (18%)

        🚶 Walked once — $800 over fair value
        📈 5 deals total · 1 live · 6 turns to close on average

        You've spent about 11 minutes texting me.

    Savings math is frozen (§4.5) — one formula, used everywhere:

        closed:  saved     = asking - closed_price
        walked:  avoided   = max(0, last_seller_price - V)
        open:    projected = asking - snapshot.offer

    `avoided` on a walked deal is real but must NEVER be summed into the
    headline "saved" number. It gets its own line, phrased honestly as
    "walked away from $800 over fair value". And "projected" is never called
    "saved".

    Sum `closed_price` (Lane A adds it to the Deal model), not a re-derivation —
    it is frozen at the moment of close precisely because a later UNDO can
    change the log it would otherwise be recomputed from (§4.3).

    That last line is deliberate: "eleven minutes for $3,940" is the value
    proposition stated as a fact about the user's own data, and it is trivially
    computable from `created_at`/`updated_at` deltas.

    STUB — headline count only.
    """
    if not deals:
        return "📊 Closer, all time\n\nNo deals yet."
    # TODO(Lane B): the §4.5 formulas, best deal, walked line, time-spent line.
    return f"📊 Closer, all time\n\n📈 {len(deals)} deals total"


def help_card() -> str:
    """Capability card. Mirrors the §4.1 trigger table in the user's language —
    what to say, not what the intent is called.

    STUB — the shape, for Lane B to write the real copy against.
    """
    return "\n".join([
        "🤝 Closer",
        "",
        "Send a listing link and I'll research it, then coach every counter.",
        "",
        "Relay what the seller says — I read the price out of plain text.",
        'Say "card" for where we stand.',
        'Say "deals" to list them, then reply with a number to switch.',
        'Say "stats" for lifetime savings.',
        'Say "undo" if you relayed something wrong.',
    ])


def onboarding() -> str:
    """First message to a phone number that has never texted us. No signup, no
    login — the phone number IS the account (§3), so this is the entire
    onboarding surface.

    STUB — Lane B owns the final copy.
    """
    return ("Send me the used-car listing link and I'll research it, "
            "then coach every counter so you don't overpay.")


__all__ = ["deal_card", "deal_list", "stats_card", "help_card", "onboarding",
           "BLOCKS", "DOT_FULL", "DOT_EMPTY"]


if __name__ == "__main__":                          # python -m app.cards --demo
    # Phase 2 gate B: prints all four cards from a fixture. Lane B extends the
    # fixture as the real renderers land.
    import sys

    if "--demo" in sys.argv:
        from .state import Deal, DealState

        d = Deal(user_id="phone:+12055550100", title="2008 Camry LE",
                 asking=6400.0, R=4750.0, V=4200.0, last_seller_price=5400.0,
                 state=DealState.NEGOTIATING)
        for card in (deal_card(d), deal_list([d], d.id), stats_card([d]),
                     help_card(), onboarding()):
            print(card)
            print("─" * 40)
