"""The engine ↔ dashboard seam.

`app.engine` returns the belief curve as two flat lists (`floor_map` = the
posterior, `floors` = its support). `static/dashboard.html` reads
`floor_map.floors` and `floor_map.p`. `app.main._floor_map` adapts between them.

This seam fails silently — a mismatched shape yields `undefined` in JS and the
chart renders blank with no error anywhere. These tests are the alarm.
"""

import json

import pytest

from app import main
from app.engine import BeliefState, Signals
from app.state import OFFER_CEILING, Deal

ASKING, R, V = 16_000.0, 13_000.0, 14_200.0
OPENING_OFFER = 12_400.0

# The scripted demo arc: an ordinary counter, a bluff with token movement, then
# a "final offer" backed by a real concession.
DEMO_ARC = [
    dict(seller_price=15_200.0, concession_abs=800.0, firmness=0.4),
    dict(seller_price=15_000.0, concession_abs=200.0, firmness=0.8, bluff_claim=True),
    dict(seller_price=14_000.0, concession_abs=1_000.0, firmness=0.9, final_claim=True),
]


def _signal_row(**overrides) -> dict:
    """A signals_log row as app.llm produces it — every key present."""
    return {"seller_price": None, "concession_abs": 0.0, "firmness": 0.0,
            "bluff_claim": False, "final_claim": False, "walk_threat": False,
            **overrides}


def _deal() -> Deal:
    deal = Deal(id="d1", user_id="u1", phone="+15555550100", asking=ASKING)
    deal.R, deal.V = R, V
    return deal


def _recommend(deal: Deal, last_user_offer: float, last_seller_price: float) -> dict:
    belief = deal.belief()
    assert belief is not None
    return belief.recommend(last_user_offer=last_user_offer,
                            last_seller_price=last_seller_price)


# ── the adapter itself ───────────────────────────────────────────────────────

def test_flat_engine_output_becomes_the_chart_shape():
    belief = BeliefState(ASKING, R, V, offer_ceiling=OFFER_CEILING)
    belief.update(Signals(**DEMO_ARC[0]))
    rec = belief.recommend(last_user_offer=OPENING_OFFER, last_seller_price=15_200.0)

    # Precondition: the engine really does hand us two flat lists.
    assert isinstance(rec["floor_map"], list)
    assert isinstance(rec["floors"], list)

    chart = main._floor_map(rec)
    assert sorted(chart) == ["floors", "p"]
    assert len(chart["floors"]) == len(chart["p"]) == len(belief.floors)


def test_curve_survives_the_adapter():
    """Rounding must not distort the posterior the chart draws."""
    belief = BeliefState(ASKING, R, V, offer_ceiling=OFFER_CEILING)
    belief.update(Signals(**DEMO_ARC[0]))
    rec = belief.recommend(last_user_offer=OPENING_OFFER, last_seller_price=15_200.0)

    chart = main._floor_map(rec)
    assert sum(chart["p"]) == pytest.approx(1.0, abs=1e-4)
    assert chart["p"] == pytest.approx(list(belief.p), abs=1e-6)
    assert chart["floors"] == pytest.approx(list(belief.floors), abs=1e-2)
    assert chart["floors"] == sorted(chart["floors"])  # x-axis must ascend


def test_adapter_passes_through_an_already_shaped_map():
    """Idempotent, so a persisted snapshot can be re-adapted without damage."""
    shaped = {"floors": [1.0, 2.0], "p": [0.4, 0.6]}
    assert main._floor_map({"floor_map": shaped}) is shaped


def test_adapter_tolerates_a_missing_curve():
    assert main._floor_map({}) == {"floors": [], "p": []}


# ── the snapshot the dashboard actually polls ────────────────────────────────

def test_snapshot_carries_every_key_the_dashboard_reads():
    deal = _deal()
    deal.signals_log.append(_signal_row(**DEMO_ARC[0]))
    rec = _recommend(deal, OPENING_OFFER, 15_200.0)

    snap = main._snapshot(deal, rec, "coach message")

    # Keys read by static/dashboard.html: draw() and render().
    for key in ("floor_map", "R", "V", "floor_point_est", "action", "offer",
                "p_accept", "coach_message"):
        assert snap.get(key) is not None, f"dashboard reads {key!r}"
    assert sorted(snap["floor_map"]) == ["floors", "p"]
    assert snap["action"] in {"COUNTER", "HOLD", "WALK", "ACCEPT"}


def test_snapshot_is_json_serializable():
    """It is persisted by the store and returned verbatim over /api/deals."""
    deal = _deal()
    deal.signals_log.append(_signal_row(**DEMO_ARC[0]))
    rec = _recommend(deal, OPENING_OFFER, 15_200.0)

    revived = json.loads(json.dumps(main._snapshot(deal, rec, "coach")))
    assert isinstance(revived["floor_map"]["p"][0], float)


def test_snapshot_prefers_the_deals_own_terms():
    """The engine echoes asking/R/V; the deal is the source of truth for them."""
    deal = _deal()
    deal.signals_log.append(_signal_row(**DEMO_ARC[0]))
    rec = _recommend(deal, OPENING_OFFER, 15_200.0)

    snap = main._snapshot(deal, rec, "coach")
    assert (snap["asking"], snap["R"], snap["V"]) == (ASKING, R, V)


# ── the demo arc must not walk ───────────────────────────────────────────────

def test_demo_arc_coaches_instead_of_walking():
    """Turn one must produce a counter.

    Under the engine's default ceiling of R, P(floor <= R) sits below the walk
    threshold before the first counter is even sent, and the coach abandons
    every negotiation on turn one. app.state.OFFER_CEILING is the guard.
    """
    deal = _deal()
    last_user_offer = OPENING_OFFER
    actions = []

    for step in DEMO_ARC:
        deal.signals_log.append(_signal_row(**step))
        rec = _recommend(deal, last_user_offer, step["seller_price"])
        actions.append(rec["action"])
        # Never coach the user above the fair value they are anchored to.
        assert rec["offer"] <= V + 1e-9
        if rec["action"] == "COUNTER":
            assert rec["offer"] > last_user_offer  # concessions move forward
            last_user_offer = rec["offer"]

    assert actions[0] == "COUNTER", f"walked on turn one: {actions}"
    assert "WALK" not in actions, f"demo arc walked: {actions}"


def test_replay_from_the_log_is_deterministic():
    """belief() rebuilds from signals_log on every request; it must be stable."""
    deal = _deal()
    for step in DEMO_ARC:
        deal.signals_log.append(_signal_row(**step))

    first = _recommend(deal, OPENING_OFFER, 14_000.0)
    second = _recommend(deal, OPENING_OFFER, 14_000.0)
    assert first == second
