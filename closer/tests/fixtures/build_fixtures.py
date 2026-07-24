"""Generate the card fixtures by driving the real production path.

    cd closer && .venv/bin/python -m tests.fixtures.build_fixtures

Lane B (`intent.py` / `cards.py`) builds against real engine output, never
invented numbers — update_1.md §6 Phase 1, Dev 2 task 1. Rather than curl a
running server, this imports `app.main.route_message` and calls it, which is
the *same* function `/simulate` and `/webhooks/linq` call. Every belief number
in the fixtures (`floor_point_est`, `floor_std`, `zopa_*`, `p_accept`, `offer`)
therefore comes out of the real `BeliefState`, and every coach line comes out of
the real drafter.

One deviation from the plan's "save `/state` output": these dump
`deal.model_dump()`, not `deal.public()`. `public()` drops `user_id` (required)
and `signals_log` (the replay source of truth), so it cannot be loaded back into
a `Deal`. `model_dump()` is a strict superset and round-trips, which is what a
fixture has to do.

Determinism: `classify_seller_message` and `draft_coach_message` hit Runware
when `RUNWARE_API_KEY` is set and fall back to the tested rules classifier /
heuristic drafter when it is not. Both paths produce the same *shape*. Rerunning
this script moves the coach prose and can nudge the signals, so the JSON is
committed and regenerated deliberately. `--offline` forces the no-network path.

The cast, matching `~/seller-agent` (update_1.md §7 D1) so the fixtures and the
live demo tell one story:

    2008 Camry LE — listed $6,400, Marcus walks at $4,750 and never says so.

Note on fair value: CLAUDE.md pins Marcus's car at "honestly worth about
$4,200". That is the seller agent's ground truth. Closer's *research* is a
separate estimate, and for a clean-title 142k LE it lands at $5,200 — which is
what makes this negotiation worth watching. The zone of agreement is thin, so
the only way to win it is to know which of his moves are real. That is the
product.

Five fixtures, chosen to cover every branch a card renderer has:

    deal_camry.json    NEGOTIATING, 4 turns, turn 3 is a bluff   ← the money card
    deal_civic.json    AWAITING_RESEARCH — snapshot is None, research is None
    deal_fresh.json    AWAITING_LINK — every optional field null
    deal_f150.json     CLOSED, under ask
    deal_tacoma.json   WALKED, he never came under fair value

The null-state fixtures exist because that is what a judge sees in the first
thirty seconds (update_1.md §6, Dev 2 done gate) — a card renderer that only
works on a finished deal is a card renderer that breaks on stage.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

if "--offline" in sys.argv:  # exercise the rules classifier + heuristic drafter
    os.environ["RUNWARE_API_KEY"] = ""

from app import research  # noqa: E402
from app import store as store_mod  # noqa: E402
from app.main import route_message  # noqa: E402  the real router
from app.state import Deal, DealState  # noqa: E402

STORE = store_mod.get_store()

USER = "phone:+12055550100"
PHONE = "+12055550100"

# ── the cars ─────────────────────────────────────────────────────────────────
# Payloads are shaped like `app.research._normalize` output, so `to_valuation`
# derives V and R here exactly the way `_do_research` does on the live path.
CAMRY_RESEARCH = {
    "facts": {"year": 2008, "make": "Toyota", "model": "Camry", "trim": "LE",
              "miles": 142_000, "title": "clean", "asking": 6400},
    "fair_value": 5200,
    "confidence": "med",
    "hidden_costs": [
        {"item": "timing belt + water pump due at 150k", "cost": 900},
        {"item": "both front struts weeping", "cost": 480},
        {"item": "tires at 4/32", "cost": 520},
    ],
    "red_flags": ["seller has owned it 4 months", "no service records after 2019"],
    "sources": [
        {"title": "KBB private party", "url": "https://www.kbb.com/toyota/camry/2008/"},
        {"title": "Edmunds appraisal", "url": "https://www.edmunds.com/toyota/camry/2008/"},
        {"title": "CarComplaints 2008 Camry",
         "url": "https://www.carcomplaints.com/Toyota/Camry/2008/"},
    ],
    "steps": [
        {"tool": "web_search", "note": "2008 Toyota Camry LE 142k private party value"},
        {"tool": "fetch_page", "note": "kbb.com/toyota/camry/2008/"},
        {"tool": "fetch_page", "note": "edmunds.com/toyota/camry/2008/"},
        {"tool": "web_search", "note": "2008 Camry common problems 140k miles"},
        {"tool": "fetch_page", "note": "carcomplaints.com/Toyota/Camry/2008/"},
    ],
    "summary": "Clean-title 2008 Camry LE at 142k. Private-party fair value $5,200; "
               "timing belt is the big one at $900.",
}

# Marcus's arc, straight from the seller agent's playbook: anchor, a shrinking
# concession, then PRESSURE WITH NO PRICE. Turn 3 is the one the whole product
# exists for — an "other buyers" claim carrying no movement, which the engine
# reads as cheap talk and the deal card calls out by name.
CAMRY_ARC = [
    "He says 6,400 is what it's worth — plenty of life left in it.",
    "He came down to 5,900 and says that's already a favor.",
    "He says three other people are coming to see it Saturday, so he's not moving.",
    "He'll do 5,400 if I pick it up tomorrow.",
]

F150_RESEARCH = {
    "facts": {"year": 2014, "make": "Ford", "model": "F-150", "trim": "XLT",
              "miles": 118_000, "title": "clean", "asking": 14_900},
    "fair_value": 13_100, "confidence": "high",
    "hidden_costs": [{"item": "cam phasers ticking on cold start", "cost": 1400}],
    "red_flags": ["cam phaser rattle on cold start"],
    "sources": [{"title": "KBB private party", "url": "https://www.kbb.com/ford/f150/2014/"}],
    "steps": [{"tool": "web_search", "note": "2014 F-150 XLT 118k private party"}],
    "summary": "2014 F-150 XLT at 118k. Fair value $13,100 before the cam phasers.",
}

TACOMA_RESEARCH = {
    "facts": {"year": 2012, "make": "Toyota", "model": "Tacoma", "trim": "SR5",
              "miles": 196_000, "title": "rebuilt", "asking": 13_500},
    "fair_value": 11_200, "confidence": "med",
    "hidden_costs": [{"item": "rear leaf pack sagging", "cost": 600}],
    "red_flags": ["rebuilt title", "frame surface rust"],
    "sources": [{"title": "KBB private party", "url": "https://www.kbb.com/toyota/tacoma/2012/"}],
    "steps": [{"tool": "web_search", "note": "2012 Tacoma SR5 rebuilt title value"}],
    "summary": "Rebuilt-title 2012 Tacoma at 196k. Fair value $11,200 and that is generous.",
}


def _negotiating(title: str, link: str, payload: dict) -> Deal:
    """A deal parked exactly where `_do_research` leaves one: valuation set from
    the payload by the real `to_valuation`, state NEGOTIATING, no turns yet."""
    val = research.to_valuation(payload)
    deal = Deal(user_id=USER, phone=PHONE, title=title, listing_link=link,
                state=DealState.NEGOTIATING,
                asking=val["asking"], V=val["V"], R=val["R"],
                research=payload, research_steps=payload.get("steps", []))
    STORE.save_deal(deal)
    print(f"  asking ${val['asking']:,.0f} · V ${val['V']:,.0f} · R ${val['R']:,.0f}")
    return deal


def _drive(deal: Deal, messages: list[str]) -> None:
    for text in messages:
        reply = route_message(deal, text, [], send=False, research_bg=False)
        STORE.save_deal(deal)
        snap = deal.snapshot or {}
        floor = snap.get("floor_point_est")
        tail = f"floor ${floor:,.0f}" if floor else deal.state.value
        print(f"  › {text[:56]:<56} {tail}")
        del reply


# A fixed clock. `Date.now()`-style drift would make every regeneration a diff,
# and the stats card's "minutes texting me" line needs real created/updated
# spans to compute from — a fixture built in one process has span 0, which is
# true of the build script and false of every real deal.
T0 = 1_753_300_000.0                                # 2025-07-23 in epoch seconds


def _age(deal: Deal, started_min_ago: float, spent_min: float) -> None:
    """Backdate a fixture's clock: created `started_min_ago` before now, with
    `spent_min` of thread time. Shaping, and labelled as such — every other
    number in these files comes out of the engine untouched."""
    deal.created_at = T0 - started_min_ago * 60.0
    deal.updated_at = deal.created_at + spent_min * 60.0
    for i, turn in enumerate(deal.feed):
        turn.ts = deal.created_at + (i + 1) * (spent_min * 60.0) / max(1, len(deal.feed))


def _dump(deal: Deal, name: str) -> None:
    path = HERE / name
    path.write_text(json.dumps(deal.model_dump(mode="json"), indent=2) + "\n")
    print(f"  → tests/fixtures/{name}")


def main() -> None:
    print("2008 Camry LE — the 4-turn arc, turn 3 is the bluff")
    camry = _negotiating("2008 Toyota Camry LE",
                         "https://www.facebook.com/marketplace/item/1102938471",
                         CAMRY_RESEARCH)
    _drive(camry, CAMRY_ARC)
    _age(camry, started_min_ago=52, spent_min=7)
    _dump(camry, "deal_camry.json")

    print("\n2016 Civic EX — mid-research (snapshot is None, research is None)")
    civic = Deal(user_id=USER, phone=PHONE, title="2016 Honda Civic EX",
                 listing_link="https://www.cars.com/vehicledetail/9f2c1a/",
                 state=DealState.AWAITING_RESEARCH, asking=11_900.0,
                 research_steps=[
                     {"tool": "web_search", "note": "2016 Civic EX private party value"},
                     {"tool": "fetch_page", "note": "kbb.com/honda/civic/2016/"},
                 ])
    STORE.save_deal(civic)
    _age(civic, started_min_ago=2, spent_min=0.5)
    _dump(civic, "deal_civic.json")

    print("\nBrand new — AWAITING_LINK, everything null")
    fresh = Deal(user_id=USER, phone=PHONE)
    STORE.save_deal(fresh)
    _age(fresh, started_min_ago=1, spent_min=0)
    _dump(fresh, "deal_fresh.json")

    print("\n2014 F-150 XLT — closed under ask")
    f150 = _negotiating("2014 Ford F-150 XLT",
                        "https://www.autotrader.com/cars-for-sale/vehicle/771823",
                        F150_RESEARCH)
    _drive(f150, [
        "He's at 14,900 and says the truck sells itself.",
        "He'll take 13,900 if I come today.",
        "13,400 and he says that's the floor.",
        "we have a deal",
    ])
    _age(f150, started_min_ago=4_300, spent_min=11)
    _dump(f150, "deal_f150.json")

    print("\n2012 Tacoma SR5 — walked, he never came under fair value")
    tacoma = _negotiating("2012 Toyota Tacoma SR5",
                          "https://www.craigslist.org/sfo/cto/d/2012-tacoma/7712.html",
                          TACOMA_RESEARCH)
    _drive(tacoma, [
        "13,500 and he says rebuilt titles don't matter on Toyotas.",
        "12,000 is as low as he'll go, final.",
        "i walked",
    ])
    _age(tacoma, started_min_ago=9_800, spent_min=6)
    _dump(tacoma, "deal_tacoma.json")

    print("\nDone. Regenerate deliberately — the JSON is committed for stable tests.")


if __name__ == "__main__":
    main()
