"""Tests for the Bayesian negotiation engine.

Organised as: grid & prior → Signals validation → update invariants → each
likelihood factor in isolation → decision layer → the scripted arc from build
spec §2.5 → robustness fuzzing.

Assertions are directional and invariant-based wherever the spec allows, so
that tuning the constants in ``engine.py`` does not require rewriting the suite.
The handful of tests that pin exact numeric bands are marked as such.
"""

from __future__ import annotations

import json
import math
from typing import NamedTuple

import numpy as np
import pytest

from app.engine import (
    CHEAP_TALK_MAX_CONCESSION_FRAC,
    GAP_MAX_FRAC,
    GAP_MIN_FRAC,
    GRID_HI_FRAC,
    GRID_LO_FRAC,
    GRID_POINTS,
    MAX_CONCESSION_FRACTION,
    PRIOR_MEAN_FRAC,
    WALK_ZOPA_THRESHOLD,
    Action,
    BeliefState,
    Signals,
    Zopa,
)

ASKING = 16_000.0
R_SPEC = 13_000.0        # build spec §2.5: fair_value - hidden_costs
R_CALIBRATED = 13_800.0  # the R the §2.5 band and §7 runbook actually imply
V = 14_200.0
OPENING_OFFER = 12_400.0


@pytest.fixture
def belief() -> BeliefState:
    return BeliefState(asking=ASKING, R=R_SPEC, V=V)


@pytest.fixture
def calibrated() -> BeliefState:
    return BeliefState(asking=ASKING, R=R_CALIBRATED, V=V)


def arc_turn_one() -> Signals:
    """Seller's opening counter: 15,200 — an 800 move off the 16,000 ask."""
    return Signals(seller_price=15_200, concession_abs=800, firmness=0.7)


def arc_turn_two() -> Signals:
    """Pure cheap talk: another buyer, no number, no movement."""
    return Signals(concession_abs=0, firmness=0.8, bluff_claim=True)


def arc_turn_three() -> Signals:
    """A real 'final offer': 14,000, backed by a 1,200 concession."""
    return Signals(seller_price=14_000, concession_abs=1_200, firmness=0.8, final_claim=True)


# ==========================================================================
# Grid & prior (§2.1)
# ==========================================================================


class TestGridAndPrior:
    def test_grid_shape_and_endpoints(self, belief):
        assert belief.floors.shape == (GRID_POINTS,)
        assert belief.floors[0] == pytest.approx(GRID_LO_FRAC * ASKING)
        assert belief.floors[-1] == pytest.approx(GRID_HI_FRAC * ASKING)

    def test_grid_is_evenly_spaced(self, belief):
        spacing = np.diff(belief.floors)
        assert np.allclose(spacing, spacing[0])
        assert spacing[0] == pytest.approx(
            (GRID_HI_FRAC - GRID_LO_FRAC) * ASKING / (GRID_POINTS - 1)
        )

    def test_prior_sums_to_one(self, belief):
        """Build spec §2.5 test 1, first half."""
        assert belief.p.sum() == pytest.approx(1.0)

    def test_prior_median_in_spec_band(self, belief):
        """Build spec §2.5 test 1, second half — pinned numeric band."""
        assert 13_500 <= belief.median() <= 14_800

    def test_prior_is_strictly_positive_and_finite(self, belief):
        assert np.all(belief.p > 0)
        assert np.all(np.isfinite(belief.p))

    def test_prior_peaks_near_configured_mean(self, belief):
        peak = belief.floors[int(np.argmax(belief.p))]
        # Peak lands on the grid point nearest 0.88·asking.
        assert abs(peak - PRIOR_MEAN_FRAC * ASKING) <= np.diff(belief.floors)[0]

    def test_prior_is_unimodal(self, belief):
        diffs = np.diff(belief.p)
        sign_changes = np.sum(np.diff(np.sign(diffs)) != 0)
        assert sign_changes <= 1

    def test_prior_std_positive_and_below_untruncated(self, belief):
        # Truncation to the grid can only shrink the spread.
        assert 0 < belief.std() < 0.10 * ASKING

    def test_prior_snapshot_is_kept_separately(self, belief):
        before = belief.prior.copy()
        belief.update(arc_turn_one())
        assert np.array_equal(belief.prior, before)
        assert not np.array_equal(belief.p, belief.prior)

    def test_prior_is_scale_invariant(self):
        small = BeliefState(asking=100, R=80, V=90)
        large = BeliefState(asking=200, R=160, V=180)
        assert np.allclose(small.p, large.p)
        assert large.median() == pytest.approx(2 * small.median())

    def test_prior_zopa_is_a_pure_cdf_lookup(self, belief):
        assert belief.zopa().probability == pytest.approx(belief.p_accept(R_SPEC))


# ==========================================================================
# Constructor validation
# ==========================================================================


class TestConstructorValidation:
    @pytest.mark.parametrize("bad", [0, -1, -16_000])
    def test_rejects_non_positive_asking(self, bad):
        with pytest.raises(ValueError, match="asking"):
            BeliefState(asking=bad, R=R_SPEC, V=V)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_rejects_non_positive_walkaway(self, bad):
        with pytest.raises(ValueError, match="R"):
            BeliefState(asking=ASKING, R=bad, V=V)

    @pytest.mark.parametrize("bad", [0, -1])
    def test_rejects_non_positive_value(self, bad):
        with pytest.raises(ValueError, match="V"):
            BeliefState(asking=ASKING, R=R_SPEC, V=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_asking(self, bad):
        with pytest.raises(ValueError):
            BeliefState(asking=bad, R=R_SPEC, V=V)

    def test_accepts_integer_inputs(self):
        state = BeliefState(asking=16_000, R=13_000, V=14_200)
        assert isinstance(state.asking, float)
        assert state.p.sum() == pytest.approx(1.0)


# ==========================================================================
# Signals validation (§2.2)
# ==========================================================================


class TestSignals:
    def test_defaults_are_inert(self):
        sig = Signals()
        assert sig.seller_price is None
        assert sig.concession_abs == 0.0
        assert sig.firmness == 0.0
        assert not (sig.bluff_claim or sig.final_claim or sig.walk_threat)

    @pytest.mark.parametrize("raw,expected", [(1.4, 1.0), (-0.3, 0.0), (0.55, 0.55)])
    def test_firmness_is_clipped_not_rejected(self, raw, expected):
        # An LLM occasionally returns 1.2; a live demo should not 500 over it.
        assert Signals(firmness=raw).firmness == pytest.approx(expected)

    @pytest.mark.parametrize("bad", [0, -1, -0.5])
    def test_rejects_non_positive_seller_price(self, bad):
        with pytest.raises(ValueError, match="positive"):
            Signals(seller_price=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_rejects_non_finite_seller_price(self, bad):
        with pytest.raises(ValueError, match="finite"):
            Signals(seller_price=bad)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_rejects_non_finite_concession(self, bad):
        with pytest.raises(ValueError, match="finite"):
            Signals(concession_abs=bad)

    def test_rejects_non_finite_firmness(self):
        with pytest.raises(ValueError, match="finite"):
            Signals(firmness=float("nan"))

    def test_negative_concession_is_allowed(self):
        # The seller raising their price is meaningful, not invalid.
        assert Signals(concession_abs=-500).concession_abs == -500

    def test_booleans_are_coerced(self):
        sig = Signals(bluff_claim=1, final_claim="yes", walk_threat=0)
        assert sig.bluff_claim is True
        assert sig.final_claim is True
        assert sig.walk_threat is False

    def test_seller_price_coerced_to_float(self):
        assert isinstance(Signals(seller_price=15_200).seller_price, float)

    def test_from_dict_roundtrip(self):
        payload = {
            "seller_price": 14_000,
            "concession_abs": 1_200,
            "firmness": 0.8,
            "bluff_claim": False,
            "final_claim": True,
            "walk_threat": False,
        }
        assert Signals.from_dict(payload).to_dict() == {**payload, "seller_price": 14_000.0}

    def test_from_dict_tolerates_missing_and_null_fields(self):
        sig = Signals.from_dict({"seller_price": None, "firmness": None})
        assert sig.seller_price is None
        assert sig.firmness == 0.0
        assert sig.concession_abs == 0.0

    def test_to_dict_is_json_serializable(self):
        json.dumps(Signals(seller_price=14_000, final_claim=True).to_dict())


# ==========================================================================
# Update invariants (§2.3)
# ==========================================================================


class TestUpdateInvariants:
    def test_posterior_normalizes_after_every_turn(self, belief):
        for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            belief.update(sig)
            assert belief.p.sum() == pytest.approx(1.0)

    def test_posterior_stays_non_negative_and_finite(self, belief):
        belief.update(arc_turn_one()).update(arc_turn_three())
        assert np.all(belief.p >= 0)
        assert np.all(np.isfinite(belief.p))

    def test_update_is_chainable(self, belief):
        assert belief.update(arc_turn_one()) is belief

    def test_update_rejects_non_signals(self, belief):
        with pytest.raises(TypeError):
            belief.update({"seller_price": 15_200})

    def test_history_records_signals_and_posterior(self, belief):
        sig = arc_turn_one()
        belief.update(sig)
        assert len(belief.history) == 1
        assert belief.history[0].signals is sig
        assert np.allclose(belief.history[0].posterior, belief.p)

    def test_history_stores_snapshots_not_live_references(self, belief):
        belief.update(arc_turn_one())
        snapshot = belief.history[0].posterior.copy()
        belief.update(arc_turn_three())
        assert np.array_equal(belief.history[0].posterior, snapshot)

    def test_history_is_tuple_compatible(self, belief):
        belief.update(arc_turn_one())
        signals, posterior = belief.history[0]  # NamedTuple unpacking
        assert isinstance(signals, Signals)
        assert posterior.shape == belief.floors.shape

    def test_empty_signals_leave_belief_untouched(self, belief):
        before = belief.p.copy()
        belief.update(Signals())
        assert np.allclose(belief.p, before)

    def test_asking_price_seeds_the_sellers_opening_quote(self, belief):
        """The listing price is the seller's first stated price, not 'n/a'."""
        assert belief.last_seller_price == ASKING

    def test_restating_the_asking_price_is_not_new_information(self, belief):
        before = belief.p.copy()
        belief.update(Signals(seller_price=ASKING, concession_abs=0, firmness=1.0))
        assert np.allclose(belief.p, before)

    def test_last_seller_price_tracks_latest_quote(self, belief):
        assert belief.last_seller_price == ASKING
        belief.update(arc_turn_one())
        assert belief.last_seller_price == 15_200
        belief.update(arc_turn_two())  # no price stated
        assert belief.last_seller_price == 15_200
        belief.update(arc_turn_three())
        assert belief.last_seller_price == 14_000


# ==========================================================================
# Likelihood factor 1: stated-price ceiling
# ==========================================================================


class TestCeilingFactor:
    def test_mass_above_stated_price_is_crushed(self, belief):
        above = belief.floors > 15_200
        before = belief.p[above].sum()
        belief.update(arc_turn_one())
        assert belief.p[above].sum() < before / 10

    def test_ceiling_is_soft_not_absolute(self, belief):
        """A mis-parsed price must never zero out the belief."""
        belief.update(Signals(seller_price=15_200, firmness=0.7))
        assert np.all(belief.p > 0)

    def test_price_below_entire_grid_is_survivable(self, belief):
        belief.update(Signals(seller_price=1.0, firmness=0.5))
        assert belief.p.sum() == pytest.approx(1.0)
        assert np.all(np.isfinite(belief.p))

    def test_absurdly_high_price_is_inert_not_destabilising(self, belief):
        """A quote above their last one is not new evidence about a lower floor."""
        before = belief.p.copy()
        belief.update(Signals(seller_price=10_000_000, firmness=0.5))
        assert np.allclose(belief.p, before)
        assert np.all(np.isfinite(belief.p))

    def test_extreme_low_price_collapses_belief_without_nan(self, belief):
        """The gap centre lands far below the grid — the underflow path."""
        belief.update(Signals(seller_price=1.0, firmness=1.0))
        assert belief.p.sum() == pytest.approx(1.0)
        assert np.all(np.isfinite(belief.p))
        assert belief.floors[0] <= belief.median() < belief.floors[1]


# ==========================================================================
# Likelihood factor 2: the gap model (the core intuition checks from §2.3)
# ==========================================================================


class TestGapModel:
    def test_firm_small_concession_shifts_mass_up(self, belief):
        """Build spec §2.5 test 2 — 'firm tiny concession ⇒ mass shifts UP'."""
        before = belief.median()
        belief.update(arc_turn_one())
        assert belief.median() > before

    def test_big_fast_concession_shifts_mass_down_relative_to_small(self):
        small = BeliefState(ASKING, R_SPEC, V)
        big = BeliefState(ASKING, R_SPEC, V)
        small.update(Signals(seller_price=15_200, concession_abs=100, firmness=0.7))
        big.update(Signals(seller_price=15_200, concession_abs=2_000, firmness=0.7))
        assert big.median() < small.median()

    def test_any_stated_price_narrows_the_belief(self, belief):
        """'⇒ posterior mass ... narrows' — a sharp likelihood always tightens."""
        before = belief.std()
        belief.update(Signals(seller_price=15_200, concession_abs=2_000, firmness=0.7))
        assert belief.std() < before

    def test_firmer_language_yields_a_sharper_posterior(self):
        soft = BeliefState(ASKING, R_SPEC, V)
        firm = BeliefState(ASKING, R_SPEC, V)
        soft.update(Signals(seller_price=15_200, firmness=0.1))
        firm.update(Signals(seller_price=15_200, firmness=0.9))
        assert firm.std() < soft.std()

    def test_credible_final_claim_spikes_the_belief(self):
        plain = BeliefState(ASKING, R_SPEC, V)
        final = BeliefState(ASKING, R_SPEC, V)
        plain.update(Signals(seller_price=14_000, concession_abs=1_200, firmness=0.8))
        final.update(
            Signals(seller_price=14_000, concession_abs=1_200, firmness=0.8, final_claim=True)
        )
        assert final.std() < plain.std()

    def test_final_claim_without_movement_does_not_spike(self):
        """'Final offer' with no concession behind it earns no extra sharpening."""
        tiny = 0.005 * ASKING  # below FINAL_CLAIM_MIN_CONCESSION_FRAC · asking
        plain = BeliefState(ASKING, R_SPEC, V)
        claimed = BeliefState(ASKING, R_SPEC, V)
        plain.update(Signals(seller_price=14_000, concession_abs=tiny, firmness=0.8))
        claimed.update(
            Signals(seller_price=14_000, concession_abs=tiny, firmness=0.8, final_claim=True)
        )
        assert claimed.std() == pytest.approx(plain.std())

    def test_gap_is_clipped_at_its_floor(self):
        """A negative concession cannot drive the expected gap below the floor."""
        clipped = BeliefState(ASKING, R_SPEC, V)
        at_floor = BeliefState(ASKING, R_SPEC, V)
        clipped.update(Signals(seller_price=15_200, concession_abs=-50_000, firmness=1.0))
        at_floor.update(
            Signals(seller_price=15_200, concession_abs=GAP_MIN_FRAC * ASKING / 0.9, firmness=1.0)
        )
        assert np.allclose(clipped.p, at_floor.p)

    def test_gap_is_clipped_at_its_ceiling(self):
        huge = BeliefState(ASKING, R_SPEC, V)
        at_cap = BeliefState(ASKING, R_SPEC, V)
        huge.update(Signals(seller_price=15_200, concession_abs=500_000, firmness=1.0))
        at_cap.update(
            Signals(seller_price=15_200, concession_abs=GAP_MAX_FRAC * ASKING / 0.9, firmness=1.0)
        )
        assert np.allclose(huge.p, at_cap.p)

    def test_gap_centre_far_below_grid_does_not_produce_nan(self, belief):
        """Log-space normalization must survive an all-underflow likelihood."""
        belief.update(Signals(seller_price=100.0, concession_abs=0, firmness=1.0))
        assert np.all(np.isfinite(belief.p))
        assert belief.p.sum() == pytest.approx(1.0)

    def test_repeated_extreme_updates_stay_normalized(self, belief):
        price = 15_500.0
        for _ in range(50):
            price -= 100
            belief.update(Signals(seller_price=price, concession_abs=3_000, firmness=1.0))
            assert belief.p.sum() == pytest.approx(1.0)
        assert np.all(np.isfinite(belief.p))


# ==========================================================================
# Likelihood factor 3: cheap talk
# ==========================================================================


class TestCheapTalk:
    def test_bluff_with_no_movement_barely_moves_the_median(self, belief):
        """Build spec §2.5 test 3, first half — the 'bluff called by math' beat."""
        belief.update(arc_turn_one())
        before = belief.median()
        belief.update(arc_turn_two())
        assert abs(belief.median() - before) / before < 0.01

    def test_bluff_tilts_toward_higher_floors(self, belief):
        belief.update(arc_turn_one())
        before = belief.median()
        belief.update(arc_turn_two())
        assert belief.median() > before  # tilt direction is up, just barely

    def test_bluff_tilt_keeps_every_grid_point_alive(self, belief):
        belief.update(arc_turn_two())
        assert np.all(belief.p > 0)

    def test_bluff_with_real_movement_is_not_cheap_talk(self, belief):
        """A bluff backed by a genuine concession is priced as a concession."""
        belief.update(arc_turn_one())
        before = belief.median()
        belief.update(
            Signals(seller_price=14_200, concession_abs=1_000, firmness=0.5, bluff_claim=True)
        )
        assert abs(belief.median() - before) / before > 0.01

    def test_cheap_talk_threshold_is_respected(self, belief):
        just_over = CHEAP_TALK_MAX_CONCESSION_FRAC * ASKING + 1
        belief.update(arc_turn_one())
        before = belief.p.copy()
        belief.update(Signals(concession_abs=just_over, bluff_claim=True, firmness=0.8))
        # No price, concession above the cheap-talk threshold → nothing fires.
        assert np.allclose(belief.p, before)

    def test_repeated_price_is_not_double_counted(self, belief):
        """Restating the same number is not new evidence about the floor."""
        belief.update(arc_turn_one())
        snapshot = belief.p.copy()
        belief.update(Signals(seller_price=15_200, concession_abs=0, firmness=0.9))
        assert np.allclose(belief.p, snapshot)

    def test_raised_price_is_not_treated_as_new_downward_evidence(self, belief):
        belief.update(arc_turn_one())
        snapshot = belief.p.copy()
        belief.update(Signals(seller_price=15_500, concession_abs=-300, firmness=0.9))
        assert np.allclose(belief.p, snapshot)

    def test_repeated_price_with_bluster_still_applies_cheap_talk(self, belief):
        belief.update(arc_turn_one())
        before = belief.median()
        belief.update(Signals(seller_price=15_200, concession_abs=0, bluff_claim=True))
        assert before < belief.median()
        assert abs(belief.median() - before) / before < 0.01

    def test_lower_price_after_a_repeat_still_updates(self, belief):
        belief.update(arc_turn_one())
        belief.update(Signals(seller_price=15_200, firmness=0.9))  # repeat, inert
        before = belief.median()
        belief.update(arc_turn_three())
        assert belief.median() < before


# ==========================================================================
# Decision layer: p_accept and ZOPA (§2.4)
# ==========================================================================


class TestPAcceptAndZopa:
    def test_p_accept_is_monotone_non_decreasing(self, belief):
        belief.update(arc_turn_one())
        offers = np.linspace(0.5 * ASKING, 1.2 * ASKING, 400)
        probs = [belief.p_accept(o) for o in offers]
        assert all(b >= a - 1e-12 for a, b in zip(probs, probs[1:]))

    def test_p_accept_below_grid_is_zero(self, belief):
        assert belief.p_accept(GRID_LO_FRAC * ASKING - 1) == 0.0

    def test_p_accept_above_grid_is_one(self, belief):
        assert belief.p_accept(GRID_HI_FRAC * ASKING + 1) == pytest.approx(1.0)

    def test_p_accept_matches_the_naive_mask_sum(self, belief):
        belief.update(arc_turn_three())
        for offer in (12_000, 13_000, 13_777, 14_500, 16_000):
            expected = belief.p[belief.floors <= offer].sum()
            assert belief.p_accept(offer) == pytest.approx(expected)

    def test_zopa_is_a_probability_with_a_band(self, belief):
        zone = belief.zopa()
        assert isinstance(zone, Zopa)
        assert 0.0 <= zone.probability <= 1.0
        assert zone.high == R_SPEC
        assert zone.low == pytest.approx(belief.quantile(0.10))

    def test_zopa_rises_as_the_seller_concedes(self, calibrated):
        before = calibrated.zopa().probability
        calibrated.update(arc_turn_one())
        mid = calibrated.zopa().probability
        calibrated.update(arc_turn_three())
        assert calibrated.zopa().probability > mid
        assert mid < before  # their first quote made a deal look *less* likely

    def test_walkaway_below_grid_gives_zero_zopa(self):
        state = BeliefState(asking=ASKING, R=0.4 * ASKING, V=V)
        assert state.zopa().probability == 0.0
        assert state.recommend()["action"] == Action.WALK.value

    def test_walkaway_above_grid_gives_certain_zopa(self):
        state = BeliefState(asking=ASKING, R=2 * ASKING, V=3 * ASKING)
        assert state.zopa().probability == pytest.approx(1.0)


# ==========================================================================
# Decision layer: quantiles
# ==========================================================================


class TestQuantiles:
    def test_quantiles_are_monotone(self, belief):
        belief.update(arc_turn_one())
        qs = [belief.quantile(q) for q in np.linspace(0.01, 0.99, 50)]
        assert all(b >= a for a, b in zip(qs, qs[1:]))

    def test_quantile_endpoints_clamp_to_the_grid(self, belief):
        assert belief.quantile(0.0) == pytest.approx(belief.floors[0])
        assert belief.quantile(1.0) == pytest.approx(belief.floors[-1])

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_quantile_rejects_out_of_range(self, belief, bad):
        with pytest.raises(ValueError):
            belief.quantile(bad)

    def test_median_of_a_symmetric_belief_is_its_centre(self, belief):
        """Mass-centred CDF must return the centre exactly, not a half-cell off."""
        centre = len(belief.floors) // 2
        symmetric = np.zeros_like(belief.floors)
        symmetric[centre - 2 : centre + 3] = [0.1, 0.2, 0.4, 0.2, 0.1]
        belief.p = symmetric
        assert belief.median() == pytest.approx(belief.floors[centre])

    def test_median_interpolates_between_grid_points(self, belief):
        belief.p = np.zeros_like(belief.floors)
        belief.p[10] = 0.5
        belief.p[11] = 0.5
        expected = (belief.floors[10] + belief.floors[11]) / 2
        assert belief.median() == pytest.approx(expected)

    def test_degenerate_single_point_belief(self, belief):
        belief.p = np.zeros_like(belief.floors)
        belief.p[7] = 1.0
        assert belief.median() == pytest.approx(belief.floors[7])
        assert belief.std() == pytest.approx(0.0)


# ==========================================================================
# Decision layer: the optimizer (§2.4)
# ==========================================================================


class TestOptimizer:
    def test_offer_never_exceeds_the_walkaway(self, belief):
        belief.update(arc_turn_three())
        belief.record_user_offer(OPENING_OFFER)
        assert belief.recommend()["offer"] <= R_SPEC + 1e-6

    def test_offer_never_bids_against_yourself(self, calibrated):
        calibrated.record_user_offer(13_000)
        calibrated.update(arc_turn_three())
        assert calibrated.recommend()["offer"] >= 13_000 - 1e-6

    def test_concession_cap_is_enforced(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_one())
        rec = calibrated.recommend()
        cap = OPENING_OFFER + MAX_CONCESSION_FRACTION * (15_200 - OPENING_OFFER)
        assert rec["action"] == Action.COUNTER.value
        assert rec["offer"] <= cap + 1e-6

    def test_offer_is_exactly_ev_optimal(self, calibrated):
        """Brute-force the feasible interval densely; the engine must match."""
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_one())
        rec = calibrated.recommend()

        lo = OPENING_OFFER
        hi = min(R_CALIBRATED, OPENING_OFFER + MAX_CONCESSION_FRACTION * (15_200 - OPENING_OFFER))
        dense = np.linspace(lo, hi, 20_001)
        best_dense = max((calibrated.V - o) * calibrated.p_accept(o) for o in dense)
        assert rec["action"] == Action.COUNTER.value
        assert rec["ev"] >= best_dense - 1e-9

    def test_optimizer_with_no_standing_offer_still_bounded(self, calibrated):
        calibrated.update(arc_turn_three())
        rec = calibrated.recommend()
        assert calibrated.floors[0] <= rec["offer"] <= R_CALIBRATED + 1e-6

    def test_infeasible_bounds_force_a_walk(self, belief):
        """Already offered above the walk-away: nothing legal is left."""
        belief.record_user_offer(R_SPEC + 500)
        belief.update(arc_turn_three())
        assert belief.recommend()["action"] == Action.WALK.value

    def test_seller_below_our_offer_caps_at_our_offer(self, calibrated):
        calibrated.record_user_offer(13_000)
        calibrated.update(arc_turn_three())
        rec = calibrated.recommend(last_seller_price=12_500)
        # Their price is under ours — take it rather than raise.
        assert rec["action"] == Action.ACCEPT.value
        assert rec["offer"] == pytest.approx(12_500)

    def test_offers_are_monotone_across_a_whole_arc(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        offers = [OPENING_OFFER]
        for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            calibrated.update(sig)
            rec = calibrated.recommend()
            if rec["action"] == Action.COUNTER.value:
                offers.append(calibrated.record_user_offer(rec["offer"]))
        assert all(b >= a for a, b in zip(offers, offers[1:]))

    def test_record_user_offer_never_decreases(self, belief):
        belief.record_user_offer(12_400)
        assert belief.record_user_offer(11_000) == 12_400
        assert belief.last_user_offer == 12_400

    @pytest.mark.parametrize("bad", [0, -100, float("nan")])
    def test_record_user_offer_validates(self, belief, bad):
        with pytest.raises(ValueError):
            belief.record_user_offer(bad)

    def test_explicit_overrides_beat_tracked_state(self, calibrated):
        calibrated.record_user_offer(12_000)
        calibrated.update(arc_turn_three())
        rec = calibrated.recommend(last_user_offer=13_500)
        assert rec["last_user_offer"] == 13_500
        assert rec["offer"] >= 13_500 - 1e-6


# ==========================================================================
# Decision layer: action selection (§2.4)
# ==========================================================================


class TestActionSelection:
    def test_low_zopa_triggers_walk(self, belief):
        belief.record_user_offer(OPENING_OFFER)
        belief.update(arc_turn_one())
        rec = belief.recommend()
        assert rec["zopa"] < WALK_ZOPA_THRESHOLD
        assert rec["action"] == Action.WALK.value

    def test_walk_restates_the_walkaway_price(self, belief):
        belief.update(arc_turn_one())
        rec = belief.recommend()
        assert rec["action"] == Action.WALK.value
        assert rec["offer"] == pytest.approx(R_SPEC)

    def test_cheap_talk_triggers_hold_at_the_standing_offer(self, calibrated):
        """Build spec §2.5 test 3, second half."""
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_one())
        rec = calibrated.recommend()
        if rec["action"] == Action.COUNTER.value:
            calibrated.record_user_offer(rec["offer"])
        standing = calibrated.last_user_offer

        calibrated.update(arc_turn_two())
        held = calibrated.recommend()
        assert held["action"] == Action.HOLD.value
        assert held["offer"] == pytest.approx(standing)

    def test_hold_needs_a_standing_offer(self, calibrated):
        calibrated.update(arc_turn_two())
        assert calibrated.recommend()["action"] != Action.HOLD.value

    def test_cheap_talk_flag_clears_after_a_real_move(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_two())
        assert calibrated.recommend()["action"] == Action.HOLD.value
        calibrated.update(arc_turn_three())
        assert calibrated.recommend()["action"] != Action.HOLD.value

    def test_accept_when_their_price_beats_every_feasible_counter(self, calibrated):
        """They landed inside R, and the concession cap leaves only long shots."""
        calibrated.record_user_offer(12_000)
        calibrated.update(Signals(seller_price=13_750, concession_abs=250, firmness=0.95))
        rec = calibrated.recommend()
        assert rec["action"] == Action.ACCEPT.value
        assert rec["offer"] == pytest.approx(13_750)
        assert rec["p_accept"] == 1.0
        assert rec["ev"] == pytest.approx(V - 13_750)

    def test_counter_preferred_when_holding_out_pays_more(self, calibrated):
        """Their price is inside R, but a likely-accepted counter still wins."""
        calibrated.record_user_offer(13_400)
        calibrated.update(Signals(seller_price=13_500, concession_abs=500, firmness=0.9))
        rec = calibrated.recommend()
        assert rec["action"] == Action.COUNTER.value
        assert rec["ev"] > V - 13_500  # strictly better than taking their price

    def test_never_accept_above_the_walkaway(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_three())  # seller at 14,000 > R 13,800
        assert calibrated.recommend()["action"] != Action.ACCEPT.value

    def test_accept_outranks_walk(self):
        """A live price at or under R is fact; ZOPA is only a prediction."""
        state = BeliefState(asking=ASKING, R=R_SPEC, V=V)
        state.update(arc_turn_one())          # drives ZOPA far below 25%
        assert state.zopa().probability < WALK_ZOPA_THRESHOLD
        rec = state.recommend(last_seller_price=12_900)
        assert rec["action"] == Action.ACCEPT.value

    def test_counter_is_the_default_action(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_three())
        rec = calibrated.recommend()
        assert rec["action"] == Action.COUNTER.value
        assert rec["ev"] > 0

    def test_non_positive_ev_forces_a_walk(self):
        """Degenerate guard: fair value below the whole grid, so no offer profits."""
        state = BeliefState(asking=ASKING, R=1.05 * ASKING, V=0.55 * ASKING)
        state.update(Signals(seller_price=0.9 * ASKING, concession_abs=500, firmness=0.2))
        rec = state.recommend()
        assert rec["zopa"] >= WALK_ZOPA_THRESHOLD  # not the ZOPA rule firing
        assert rec["action"] == Action.WALK.value


# ==========================================================================
# recommend() payload contract (consumed by the dashboard and the drafter)
# ==========================================================================


class TestRecommendPayload:
    REQUIRED = {
        "action",
        "offer",
        "p_accept",
        "ev",
        "zopa",
        "floor_map",
        "floor_point_est",
    }

    def test_contains_every_spec_required_key(self, belief):
        assert self.REQUIRED <= set(belief.recommend())

    def test_is_json_serializable(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_three())
        payload = json.dumps(calibrated.recommend())
        assert json.loads(payload)["action"] in {a.value for a in Action}

    def test_floor_map_aligns_with_the_grid(self, belief):
        rec = belief.recommend()
        assert len(rec["floor_map"]) == len(rec["floors"]) == GRID_POINTS
        assert sum(rec["floor_map"]) == pytest.approx(1.0)

    def test_point_estimate_is_the_posterior_median(self, belief):
        belief.update(arc_turn_three())
        assert belief.recommend()["floor_point_est"] == pytest.approx(belief.median())

    def test_carries_context_for_the_message_drafter(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_one())
        rec = calibrated.recommend()
        assert rec["asking"] == ASKING and rec["R"] == R_CALIBRATED and rec["V"] == V
        assert rec["last_seller_price"] == 15_200
        assert rec["turns"] == 1
        assert isinstance(rec["rationale"], str) and rec["rationale"]

    def test_probabilities_are_in_range(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            calibrated.update(sig)
            rec = calibrated.recommend()
            assert 0.0 <= rec["p_accept"] <= 1.0
            assert 0.0 <= rec["zopa"] <= 1.0


# ==========================================================================
# The scripted arc from build spec §2.5
# ==========================================================================


class TestScriptedArcSpecWalkaway:
    """§2.5 with R = 13,000 and the default spec-literal ceiling.

    Every belief-level assertion in §2.5 holds here. The two *decision-level*
    expectations (HOLD on turn 2, final counter in [13,300, 13,800]) cannot,
    because §2.4's ``o <= R`` caps offers at 13,000 — the engine correctly walks
    instead, pinned in ``test_spec_walkaway_walks_immediately``.

    Both decision-level expectations DO hold under ``offer_ceiling="V"`` with the
    same R — see ``TestOfferCeiling`` — or under a higher R, see
    ``TestScriptedArcCalibratedWalkaway``.
    """

    def test_median_rises_then_barely_moves_then_drops(self, belief):
        prior_median = belief.median()

        belief.update(arc_turn_one())
        after_quote = belief.median()
        assert after_quote > prior_median  # §2.5 test 2

        belief.update(arc_turn_two())
        after_bluff = belief.median()
        assert abs(after_bluff - after_quote) / after_quote < 0.01  # §2.5 test 3

        std_before_final = belief.std()
        belief.update(arc_turn_three())
        assert belief.median() < 14_000  # §2.5 test 4
        assert belief.std() <= 0.70 * std_before_final  # std shrinks >= 30%

    def test_spec_walkaway_walks_immediately(self, belief):
        """R = 13,000 sits below the prior's 25th percentile for this listing."""
        belief.record_user_offer(OPENING_OFFER)
        belief.update(arc_turn_one())
        assert belief.recommend()["action"] == Action.WALK.value

    def test_offer_invariants_hold_across_the_arc(self, belief):
        belief.record_user_offer(OPENING_OFFER)
        previous = OPENING_OFFER
        for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            belief.update(sig)
            rec = belief.recommend()
            assert rec["offer"] <= R_SPEC + 1e-6      # §2.5 test 5, first half
            assert rec["offer"] >= previous - 1e-6    # §2.5 test 5, second half
            if rec["action"] == Action.COUNTER.value:
                previous = belief.record_user_offer(rec["offer"])


class TestScriptedArcCalibratedWalkaway:
    """The same arc at R = 13,800 — the value §2.5 test 5 and §7 imply."""

    def _run(self, state: BeliefState) -> list[dict]:
        state.record_user_offer(OPENING_OFFER)
        out = []
        for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            state.update(sig)
            rec = state.recommend()
            if rec["action"] == Action.COUNTER.value:
                state.record_user_offer(rec["offer"])
            out.append(rec)
        return out

    def test_arc_produces_the_intended_narrative(self, calibrated):
        first, second, third = self._run(calibrated)
        assert first["action"] == Action.COUNTER.value
        assert second["action"] == Action.HOLD.value  # bluff called by math
        # Their "final 14,000" makes our standing number the EV-optimal one:
        # hold rather than bid against ourselves.
        assert third["action"] == Action.HOLD.value
        assert third["p_accept"] > 0.85

    def test_final_counter_lands_in_the_spec_band(self, calibrated):
        """§2.5 test 5 — pinned numeric band [13,300, 13,800]."""
        final = self._run(calibrated)[-1]
        assert 13_300 <= final["offer"] <= 13_800

    def test_deal_looks_likely_by_the_end(self, calibrated):
        assert self._run(calibrated)[-1]["zopa"] > 0.75

    def test_belief_collapses_onto_a_tight_band(self, calibrated):
        prior_std = BeliefState(ASKING, R_CALIBRATED, V).std()
        self._run(calibrated)
        assert calibrated.std() < 0.5 * prior_std
        assert calibrated.median() < 14_000

    def test_seller_accepting_closes_the_loop(self, calibrated):
        self._run(calibrated)
        standing = calibrated.last_user_offer
        rec = calibrated.recommend(last_seller_price=standing)
        assert rec["action"] == Action.ACCEPT.value
        assert rec["offer"] == pytest.approx(standing)


# ==========================================================================
# The math itself: engine vs. an independent reference
# ==========================================================================


def _reference_posterior(state: BeliefState, sig: Signals) -> np.ndarray:
    """Build spec §2.3 written out literally and multiplicatively.

    No log space, no max-subtraction, no repeat guard — the formula exactly as
    published. Only valid for inputs that do not underflow float64, which is why
    the cases below stay near the grid.
    """
    floors, asking = state.floors, state.asking
    likelihood = np.ones_like(floors)

    if sig.seller_price is not None:
        likelihood[floors > sig.seller_price] *= 0.02
        gap = np.clip(
            0.9 * sig.concession_abs + (1 - sig.firmness) * 0.06 * asking,
            0.01 * asking,
            0.18 * asking,
        )
        sigma = 0.05 * asking * (1.5 - sig.firmness)
        if sig.final_claim and sig.concession_abs > 0.01 * asking:
            sigma *= 0.6
        likelihood *= np.exp(
            -(((sig.seller_price - gap) - floors) ** 2) / (2 * sigma**2)
        )

    posterior = state.p * likelihood
    return posterior / posterior.sum()


class TestAgainstReferenceImplementation:
    """The log-space rewrite must be algebraically identical to the spec."""

    CASES = [
        Signals(seller_price=15_200, concession_abs=800, firmness=0.7),
        Signals(seller_price=14_000, concession_abs=1_200, firmness=0.8, final_claim=True),
        Signals(seller_price=14_000, concession_abs=100, firmness=0.8, final_claim=True),
        Signals(seller_price=13_000, concession_abs=3_000, firmness=0.1),
        Signals(seller_price=15_900, concession_abs=0, firmness=0.0),
        Signals(seller_price=12_500, concession_abs=-400, firmness=1.0),
        Signals(seller_price=15_000, concession_abs=50_000, firmness=0.5),
    ]

    @pytest.mark.parametrize("sig", CASES, ids=lambda s: f"price={s.seller_price:.0f}")
    def test_matches_the_literal_formula(self, sig):
        state = BeliefState(ASKING, R_SPEC, V)
        expected = _reference_posterior(state, sig)
        state.update(sig)
        assert np.allclose(state.p, expected, rtol=1e-10, atol=1e-15)

    @pytest.mark.parametrize("sig", CASES, ids=lambda s: f"price={s.seller_price:.0f}")
    def test_matches_the_literal_formula_mid_conversation(self, sig):
        state = BeliefState(ASKING, R_SPEC, V)
        state.update(Signals(seller_price=15_950, concession_abs=50, firmness=0.3))
        expected = _reference_posterior(state, sig)
        state.update(sig)
        assert np.allclose(state.p, expected, rtol=1e-10, atol=1e-15)

    def test_posterior_mean_matches_gaussian_conjugacy(self):
        """Prior × gap likelihood is a Gaussian product; check the closed form.

        Chosen so the stated-price ceiling and the grid edges are both far from
        the bulk of the mass, leaving discretization as the only real error.
        """
        state = BeliefState(ASKING, R_SPEC, V)
        sig = Signals(seller_price=15_900, concession_abs=2_000, firmness=0.5)
        state.update(sig)

        prior_mean, prior_sigma = 0.88 * ASKING, 0.10 * ASKING
        gap = 0.9 * 2_000 + 0.5 * 0.06 * ASKING
        like_mean = 15_900 - gap
        like_sigma = 0.05 * ASKING * (1.5 - 0.5)

        wp, wl = prior_sigma**-2, like_sigma**-2
        analytic_mean = (prior_mean * wp + like_mean * wl) / (wp + wl)
        analytic_sigma = (wp + wl) ** -0.5

        assert state.mean() == pytest.approx(analytic_mean, rel=0.005)
        assert state.std() == pytest.approx(analytic_sigma, rel=0.05)

    def test_bayes_is_order_invariant_for_independent_evidence(self):
        """Two disjoint pieces of evidence must commute."""
        price_move = Signals(seller_price=14_500, concession_abs=1_500, firmness=0.6)
        pure_bluff = Signals(concession_abs=0, firmness=0.9, bluff_claim=True)

        forward = BeliefState(ASKING, R_SPEC, V)
        forward.update(price_move).update(pure_bluff)

        backward = BeliefState(ASKING, R_SPEC, V)
        backward.update(pure_bluff).update(price_move)

        assert np.allclose(forward.p, backward.p)

    def test_cheap_talk_tilt_is_the_specified_magnitude(self, belief):
        """The bluff factor must stay a whisper — do not strengthen it."""
        floors = belief.floors
        expected = 1 + 0.04 * (floors - floors.mean()) / floors.std()
        before = belief.p.copy()
        belief.update(Signals(concession_abs=0, bluff_claim=True))
        reference = before * expected
        assert np.allclose(belief.p, reference / reference.sum())
        assert expected.max() < 1.08 and expected.min() > 0.92


# ==========================================================================
# offer_ceiling: the R-vs-V product decision, made explicit
# ==========================================================================


class TestOfferCeiling:
    """§2.4 caps offers at R; §2.5 expects a counter above R. Both are supported.

    See the "R as a ceiling" section of the engine docstring for why the spec
    contradicts itself and why this is a constructor argument.
    """

    def _run_spec_arc(self, ceiling: str) -> list[dict]:
        state = BeliefState(ASKING, R_SPEC, V, offer_ceiling=ceiling)
        state.record_user_offer(OPENING_OFFER)
        out = []
        for signals in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            state.update(signals)
            rec = state.recommend()
            if rec["action"] == Action.COUNTER.value:
                state.record_user_offer(rec["offer"])
            out.append(rec)
        return out

    def test_defaults_to_the_spec_literal_ceiling(self, belief):
        assert belief.offer_ceiling == "R"
        assert belief.ceiling == R_SPEC

    def test_value_ceiling_raises_the_limit_to_fair_value(self):
        state = BeliefState(ASKING, R_SPEC, V, offer_ceiling="V")
        assert state.ceiling == V

    @pytest.mark.parametrize("bad", ["r", "v", "asking", "", None])
    def test_rejects_an_unknown_ceiling(self, bad):
        with pytest.raises(ValueError, match="offer_ceiling"):
            BeliefState(ASKING, R_SPEC, V, offer_ceiling=bad)

    def test_value_ceiling_permits_offers_above_R_but_never_above_V(self):
        recs = self._run_spec_arc("V")
        assert max(r["offer"] for r in recs) > R_SPEC
        for rec in recs:
            assert rec["offer"] <= V + 1e-6

    def test_spec_ceiling_never_offers_above_R(self):
        for rec in self._run_spec_arc("R"):
            assert rec["offer"] <= R_SPEC + 1e-6

    def test_value_ceiling_reproduces_the_spec_band_with_the_spec_walkaway(self):
        """§2.5 test 5 satisfied at R = 13,000 — no re-tuning of R required."""
        recs = self._run_spec_arc("V")
        assert recs[0]["action"] == Action.COUNTER.value
        assert recs[1]["action"] == Action.HOLD.value  # bluff called by math
        assert 13_300 <= recs[-1]["offer"] <= 13_800

    def test_spec_ceiling_walks_where_the_value_ceiling_keeps_going(self):
        assert self._run_spec_arc("R")[0]["action"] == Action.WALK.value
        assert self._run_spec_arc("V")[0]["action"] != Action.WALK.value

    def test_zopa_always_measures_against_R_not_the_ceiling(self):
        """The reported 'will we hit our number' figure is R-relative in both modes."""
        spec = BeliefState(ASKING, R_SPEC, V, offer_ceiling="R")
        value = BeliefState(ASKING, R_SPEC, V, offer_ceiling="V")
        for state in (spec, value):
            state.update(arc_turn_one())
        assert spec.zopa().probability == pytest.approx(value.zopa().probability)
        assert spec.zopa().high == value.zopa().high == R_SPEC

    def test_p_close_tracks_the_enforced_ceiling(self):
        spec = BeliefState(ASKING, R_SPEC, V, offer_ceiling="R")
        value = BeliefState(ASKING, R_SPEC, V, offer_ceiling="V")
        for state in (spec, value):
            state.update(arc_turn_one())
        spec_rec, value_rec = spec.recommend(), value.recommend()
        assert spec_rec["p_close"] == pytest.approx(spec_rec["zopa"])
        assert value_rec["p_close"] > value_rec["zopa"]
        assert value_rec["ceiling"] == V

    def test_accept_respects_the_ceiling_not_R(self):
        """A price between R and V is acceptable under V, refused under R."""
        firm_seller = Signals(seller_price=13_900, concession_abs=50, firmness=1.0)
        assert R_SPEC < 13_900 < V

        permissive = BeliefState(ASKING, R_SPEC, V, offer_ceiling="V")
        permissive.record_user_offer(12_000)
        permissive.update(firm_seller)
        taken = permissive.recommend()
        assert taken["action"] == Action.ACCEPT.value
        assert taken["offer"] == pytest.approx(13_900)

        strict = BeliefState(ASKING, R_SPEC, V, offer_ceiling="R")
        strict.record_user_offer(12_000)
        strict.update(firm_seller)
        assert strict.recommend()["action"] != Action.ACCEPT.value

    def test_ceiling_mode_does_not_change_the_belief(self):
        """It is a decision-layer policy only — the posterior is untouched."""
        spec = BeliefState(ASKING, R_SPEC, V, offer_ceiling="R")
        value = BeliefState(ASKING, R_SPEC, V, offer_ceiling="V")
        for state in (spec, value):
            for signals in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
                state.update(signals)
        assert np.array_equal(spec.p, value.p)


class TestNamingAffordances:
    def test_as_dict_is_an_alias_for_to_dict(self):
        sig = Signals(seller_price=15_200, concession_abs=800, firmness=0.7)
        assert sig.as_dict() == sig.to_dict()

    def test_percentile_is_an_alias_for_quantile(self, belief):
        assert belief.percentile(0.10) == belief.quantile(0.10)
        assert belief.percentile(0.50) == belief.median()

    def test_floor_p10_is_exposed_for_the_chart(self, belief):
        rec = belief.recommend()
        assert rec["floor_p10"] == pytest.approx(belief.percentile(0.10))
        assert rec["floor_p10"] == rec["zopa_low"]


# ==========================================================================
# Cross-vertical: the engine sees numbers, not products
# ==========================================================================


class Scenario(NamedTuple):
    name: str
    asking: float
    value: float
    walkaway: float
    opening: float
    arc: list[Signals]


def _scenario(name, asking, value, walkaway, opening, moves) -> Scenario:
    return Scenario(
        name=name,
        asking=asking,
        value=value,
        walkaway=walkaway,
        opening=opening,
        arc=[
            Signals(
                seller_price=price,
                concession_abs=concession,
                firmness=firmness,
                bluff_claim=bluff,
                final_claim=final,
            )
            for price, concession, firmness, bluff, final in moves
        ],
    )


SCENARIOS = [
    _scenario(
        "laptop", 900, 840, 780, 700,
        [(860, 40, 0.6, False, False), (None, 0, 0.8, True, False), (810, 50, 0.85, False, True)],
    ),
    _scenario(
        "motorcycle", 4_200, 3_900, 3_650, 3_100,
        [(4_000, 200, 0.7, False, False), (None, 0, 0.8, True, False), (3_750, 250, 0.8, False, True)],
    ),
    _scenario(
        "used_car", 16_000, 14_200, 13_800, 12_400,
        [(15_200, 800, 0.7, False, False), (None, 0, 0.8, True, False), (14_000, 1_200, 0.8, False, True)],
    ),
    _scenario(
        "house", 625_000, 600_000, 545_000, 500_000,
        [(600_000, 25_000, 0.7, False, False), (None, 0, 0.8, True, False), (565_000, 35_000, 0.8, False, True)],
    ),
    _scenario(
        "concert_ticket", 320, 300, 275, 240,
        [(300, 20, 0.5, False, False), (None, 0, 0.9, True, False), (285, 15, 0.9, False, True)],
    ),
]


class TestCrossVertical:
    """Nothing in the engine is car-specific. Only ratios to ``asking`` matter.

    The vertical restriction in the build spec is a product decision — it scopes
    the research module and the LLM prompts — not a property of this module.
    """

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
    def test_arc_holds_every_invariant(self, scenario):
        state = BeliefState(scenario.asking, scenario.walkaway, scenario.value)
        standing = state.record_user_offer(scenario.opening)

        for signals in scenario.arc:
            state.update(signals)
            rec = state.recommend()

            assert state.p.sum() == pytest.approx(1.0)
            assert np.all(np.isfinite(state.p))
            assert 0.0 <= rec["p_accept"] <= 1.0
            assert 0.0 <= rec["zopa"] <= 1.0
            assert rec["offer"] <= state.R + 1e-6 * scenario.asking
            assert rec["offer"] >= standing - 1e-6 * scenario.asking
            if rec["action"] == Action.COUNTER.value:
                standing = state.record_user_offer(rec["offer"])

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
    def test_evidence_sharpens_the_belief(self, scenario):
        """Every informative turn must leave us less uncertain, not more."""
        state = BeliefState(scenario.asking, scenario.walkaway, scenario.value)
        before = state.std()
        for signals in scenario.arc:
            state.update(signals)
        assert state.std() < 0.5 * before

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
    def test_arc_closes_below_asking(self, scenario):
        """A completed negotiation must land under the list price."""
        state = BeliefState(scenario.asking, scenario.walkaway, scenario.value)
        state.record_user_offer(scenario.opening)
        for signals in scenario.arc:
            state.update(signals)
            rec = state.recommend()
            if rec["action"] == Action.COUNTER.value:
                state.record_user_offer(rec["offer"])
        assert scenario.opening <= state.last_user_offer < scenario.asking
        assert state.last_user_offer <= scenario.walkaway

    def test_a_laptop_and_a_house_negotiate_identically(self):
        """Exact scale invariance: multiply every price by 1,000, get the same run.

        Same normalized belief, same action, proportional offers, identical
        probabilities — at every turn.
        """
        k = 1_000.0
        laptop = SCENARIOS[0]
        small = BeliefState(laptop.asking, laptop.walkaway, laptop.value)
        large = BeliefState(laptop.asking * k, laptop.walkaway * k, laptop.value * k)
        small.record_user_offer(laptop.opening)
        large.record_user_offer(laptop.opening * k)

        for signals in laptop.arc:
            small.update(signals)
            large.update(
                Signals(
                    seller_price=None if signals.seller_price is None else signals.seller_price * k,
                    concession_abs=signals.concession_abs * k,
                    firmness=signals.firmness,
                    bluff_claim=signals.bluff_claim,
                    final_claim=signals.final_claim,
                )
            )

            assert np.allclose(small.p, large.p)
            small_rec, large_rec = small.recommend(), large.recommend()
            assert small_rec["action"] == large_rec["action"]
            assert large_rec["offer"] == pytest.approx(small_rec["offer"] * k)
            assert large_rec["p_accept"] == pytest.approx(small_rec["p_accept"])
            assert large_rec["zopa"] == pytest.approx(small_rec["zopa"])
            assert large_rec["floor_point_est"] == pytest.approx(
                small_rec["floor_point_est"] * k
            )
            if small_rec["action"] == Action.COUNTER.value:
                small.record_user_offer(small_rec["offer"])
                large.record_user_offer(large_rec["offer"])

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
    def test_a_generous_walkaway_is_never_worse_than_a_tight_one(self, scenario):
        """ZOPA must rise monotonically with the walk-away price."""
        probabilities = []
        for ratio in (0.78, 0.82, 0.86, 0.90, 0.94):
            state = BeliefState(scenario.asking, ratio * scenario.asking, scenario.value)
            for signals in scenario.arc:
                state.update(signals)
            probabilities.append(state.zopa().probability)
        assert all(b >= a for a, b in zip(probabilities, probabilities[1:]))

    def test_walk_is_a_signal_not_a_terminal_state(self):
        """A seller who later concedes must be able to revive a dead-looking deal."""
        house = SCENARIOS[3]
        state = BeliefState(house.asking, house.walkaway, house.value)
        state.record_user_offer(house.opening)

        state.update(house.arc[0])  # 600k on a 625k ask — barely a move
        assert state.recommend()["action"] == Action.WALK.value

        state.update(house.arc[2])  # 565k, final, real concession
        revived = state.recommend()
        assert revived["action"] == Action.COUNTER.value
        assert revived["zopa"] > WALK_ZOPA_THRESHOLD


# ==========================================================================
# Edge cases and documented non-behaviour
# ==========================================================================


class TestEdgeCases:
    def test_recommend_before_any_seller_message(self, calibrated):
        """The prior alone is a valid state to advise from."""
        rec = calibrated.recommend()
        assert rec["turns"] == 0
        assert rec["action"] in {a.value for a in Action}
        assert rec["floor_point_est"] == pytest.approx(calibrated.median())

    def test_recommend_does_not_mutate_the_belief(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        calibrated.update(arc_turn_one())
        snapshot = calibrated.p.copy()
        for _ in range(3):
            calibrated.recommend()
        assert np.array_equal(calibrated.p, snapshot)
        assert calibrated.last_user_offer == OPENING_OFFER

    def test_engine_is_deterministic(self):
        def run() -> np.ndarray:
            state = BeliefState(ASKING, R_CALIBRATED, V)
            for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
                state.update(sig)
            return state.p

        assert np.array_equal(run(), run())

    def test_history_replays_to_the_same_belief(self, calibrated):
        for sig in (arc_turn_one(), arc_turn_two(), arc_turn_three()):
            calibrated.update(sig)
        replay = BeliefState(ASKING, R_CALIBRATED, V)
        for turn in calibrated.history:
            replay.update(turn.signals)
        assert np.allclose(replay.p, calibrated.p)
        assert np.allclose(calibrated.history[-1].posterior, calibrated.p)

    def test_walk_threat_is_carried_but_does_not_move_the_math(self, belief):
        """Documented gap: the schema collects it, §2.3 never consumes it."""
        quiet = BeliefState(ASKING, R_SPEC, V)
        threatening = BeliefState(ASKING, R_SPEC, V)
        quiet.update(Signals(seller_price=15_200, concession_abs=800, firmness=0.7))
        threatening.update(
            Signals(seller_price=15_200, concession_abs=800, firmness=0.7, walk_threat=True)
        )
        assert np.allclose(quiet.p, threatening.p)

    def test_every_flag_set_at_once_is_survivable(self, belief):
        belief.update(
            Signals(
                seller_price=14_000,
                concession_abs=2_000,
                firmness=1.0,
                bluff_claim=True,
                final_claim=True,
                walk_threat=True,
            )
        )
        assert belief.p.sum() == pytest.approx(1.0)
        assert belief.recommend()["action"] in {a.value for a in Action}

    def test_consecutive_bluffs_stay_negligible(self, belief):
        belief.update(arc_turn_one())
        before = belief.median()
        for _ in range(3):
            belief.update(arc_turn_two())
        assert abs(belief.median() - before) / before < 0.02

    @pytest.mark.parametrize("asking", [10.0, 1_000.0, 1e6, 1e9])
    def test_works_across_wildly_different_price_scales(self, asking):
        state = BeliefState(asking=asking, R=0.85 * asking, V=0.9 * asking)
        state.record_user_offer(0.7 * asking)
        state.update(
            Signals(seller_price=0.95 * asking, concession_abs=0.05 * asking, firmness=0.7)
        )
        rec = state.recommend()
        assert state.p.sum() == pytest.approx(1.0)
        assert math.isfinite(rec["offer"])
        assert rec["offer"] <= state.R + 1e-6 * asking

    def test_zero_gap_between_offers_caps_at_the_standing_offer(self, calibrated):
        calibrated.update(arc_turn_three())
        calibrated.record_user_offer(14_000)  # exactly the seller's price
        rec = calibrated.recommend()
        # Gap is zero, so no concession is permitted; their price is above R.
        assert rec["offer"] <= 14_000 + 1e-6

    def test_zopa_band_low_is_below_the_median(self, calibrated):
        calibrated.update(arc_turn_one())
        zone = calibrated.zopa()
        assert zone.low < calibrated.median()

    def test_walkaway_exactly_on_a_grid_point(self):
        state = BeliefState(asking=ASKING, R=13_800.0, V=V)  # 9600 + 120*35
        on_grid = state.floors[np.isclose(state.floors, 13_800.0)]
        assert on_grid.size == 1
        # The walk-away price itself must count as acceptable.
        assert state.p_accept(13_800.0) >= state.p[: 35 + 1].sum() - 1e-12

    def test_seller_price_exactly_on_a_grid_point(self, belief):
        belief.update(Signals(seller_price=13_800.0, concession_abs=500, firmness=0.6))
        assert belief.p.sum() == pytest.approx(1.0)

    def test_belief_survives_a_seller_who_only_ever_bluffs(self, calibrated):
        calibrated.record_user_offer(OPENING_OFFER)
        for _ in range(10):
            calibrated.update(arc_turn_two())
        rec = calibrated.recommend()
        assert calibrated.p.sum() == pytest.approx(1.0)
        assert rec["action"] == Action.HOLD.value
        assert rec["offer"] == pytest.approx(OPENING_OFFER)

    def test_action_enum_is_json_safe(self):
        assert json.dumps([a for a in Action]) == '["COUNTER", "HOLD", "WALK", "ACCEPT"]'


# ==========================================================================
# Robustness fuzzing
# ==========================================================================


class TestFuzz:
    def test_random_arcs_never_break_the_invariants(self):
        rng = np.random.default_rng(20260724)
        for _ in range(300):
            asking = float(rng.uniform(2_000, 90_000))
            value = asking * float(rng.uniform(0.7, 1.0))
            walkaway = value * float(rng.uniform(0.7, 1.05))
            state = BeliefState(asking=asking, R=walkaway, V=value)

            previous_offer = None
            if rng.random() < 0.7:
                previous_offer = state.record_user_offer(asking * float(rng.uniform(0.5, 0.9)))

            for _ in range(int(rng.integers(1, 7))):
                price = None
                if rng.random() < 0.75:
                    price = float(rng.uniform(0.3, 1.4)) * asking
                state.update(
                    Signals(
                        seller_price=price,
                        concession_abs=float(rng.normal(0, 0.05 * asking)),
                        firmness=float(rng.uniform(-0.2, 1.2)),
                        bluff_claim=bool(rng.random() < 0.3),
                        final_claim=bool(rng.random() < 0.3),
                        walk_threat=bool(rng.random() < 0.2),
                    )
                )

                assert np.all(np.isfinite(state.p))
                assert np.all(state.p >= 0)
                assert state.p.sum() == pytest.approx(1.0)

                rec = state.recommend()
                assert rec["action"] in {a.value for a in Action}
                assert math.isfinite(rec["offer"])
                assert 0.0 <= rec["p_accept"] <= 1.0
                assert 0.0 <= rec["zopa"] <= 1.0
                assert math.isfinite(rec["floor_point_est"])

                if rec["action"] == Action.COUNTER.value:
                    assert rec["offer"] <= state.R + 1e-6
                    if previous_offer is not None:
                        assert rec["offer"] >= previous_offer - 1e-6
                    previous_offer = state.record_user_offer(rec["offer"])

    def test_long_conversations_stay_stable(self):
        rng = np.random.default_rng(7)
        state = BeliefState(asking=ASKING, R=R_CALIBRATED, V=V)
        price = ASKING
        for _ in range(200):
            step = float(rng.uniform(0, 200))
            price = max(1.0, price - step)
            state.update(
                Signals(seller_price=price, concession_abs=step, firmness=float(rng.random()))
            )
            assert state.p.sum() == pytest.approx(1.0)
        assert np.all(np.isfinite(state.p))
        assert len(state.history) == 200
