"""Engine tests — assert DIRECTIONAL behavior on a scripted seller arc, not exact
numbers. Scenario (build prompt §2.5): asking 16000, R 13000, V 14200.

The seller arc, turn by turn:
  1. states 15200 with a small concession, firm-ish  -> belief shifts UP
  2. bluffs ("another buyer") with no movement        -> belief barely moves, HOLD
  3. "14,000, final" with a real 1200 concession      -> belief DROPS & narrows
"""

import numpy as np
import pytest

from app.engine import BeliefState, Signals

ASKING, R, V = 16000, 13000, 14200


@pytest.fixture
def belief():
    return BeliefState(ASKING, R, V)


def test_1_prior_is_valid(belief):
    assert belief.p.shape == (61,)
    assert belief.p.sum() == pytest.approx(1.0, abs=1e-9)
    assert np.all(belief.p >= 0)
    assert 13500 <= belief.median() <= 14800


def test_2_firm_small_concession_shifts_belief_up(belief):
    prior_median = belief.median()
    belief.update(Signals(seller_price=15200, concession_abs=800, firmness=0.7))
    assert belief.median() > prior_median


def test_3_bluff_no_movement_barely_moves_and_holds(belief):
    belief.update(Signals(seller_price=15200, concession_abs=800, firmness=0.7))
    m_before = belief.median()

    belief.update(Signals(seller_price=None, concession_abs=0.0,
                          firmness=0.8, bluff_claim=True))
    # Posterior median must move less than 1% — the "bluff called by math" beat.
    assert abs(belief.median() - m_before) / m_before < 0.01

    rec = belief.recommend(last_user_offer=13000, last_seller_price=15200)
    assert rec["action"] == "HOLD"


def test_4_real_final_concession_drops_and_narrows(belief):
    belief.update(Signals(seller_price=15200, concession_abs=800, firmness=0.7))
    belief.update(Signals(seller_price=None, concession_abs=0.0,
                          firmness=0.8, bluff_claim=True))
    std_before = belief.std()

    belief.update(Signals(seller_price=14000, concession_abs=1200,
                          firmness=0.5, final_claim=True))
    assert belief.median() < 14000                 # mass shifts DOWN
    assert belief.std() <= 0.70 * std_before        # and narrows by >= 30%


def test_5_recommendation_is_bounded_and_lands_in_band(belief):
    # Every recommended offer stays legal: never above fair value V, never a
    # downward bid against ourselves.
    b = belief
    prev_user_offer = 12400

    b.update(Signals(seller_price=15200, concession_abs=800, firmness=0.7))
    r1 = b.recommend(last_user_offer=prev_user_offer, last_seller_price=15200)
    assert prev_user_offer <= r1["offer"] <= V

    b.update(Signals(seller_price=None, concession_abs=0.0,
                     firmness=0.8, bluff_claim=True))
    r2 = b.recommend(last_user_offer=13000, last_seller_price=15200)
    assert 13000 <= r2["offer"] <= V

    b.update(Signals(seller_price=14000, concession_abs=1200,
                     firmness=0.5, final_claim=True))
    r3 = b.recommend(last_user_offer=13000, last_seller_price=14000)
    assert r3["action"] in ("COUNTER", "ACCEPT")
    assert 13000 <= r3["offer"] <= V
    # With this arc the closing counter lands in the credible split band.
    assert 13300 <= r3["offer"] <= 13800


def test_zopa_rises_as_seller_caves(belief):
    """ZOPA (P(floor <= R)) should be higher after the 'final' cave than at the
    firm-anchor stage — the deal becomes more likely, which the dashboard shows."""
    belief.update(Signals(seller_price=15200, concession_abs=800, firmness=0.7))
    z_anchor = belief.zopa()
    belief.update(Signals(seller_price=None, concession_abs=0.0,
                          firmness=0.8, bluff_claim=True))
    belief.update(Signals(seller_price=14000, concession_abs=1200,
                          firmness=0.5, final_claim=True))
    assert belief.zopa() > z_anchor
