"""Closer — Bayesian negotiation engine.

Pure numpy. Zero network calls. This module must never import httpx, fastapi,
or the Runware client: it is the deterministic, inspectable core of the product. Every
number a user is shown originates here or in the expert payload — the LLM only
translates language into ``Signals`` on the way in and prose on the way out.

The model
---------
The seller has a hidden reservation price ``f`` (their "floor") — the lowest
number they would actually accept. We hold a belief distribution ``p(f)`` over a
discrete price grid, start from a truncated-normal prior anchored on the asking
price, and multiply in a likelihood after every seller message::

    p_posterior(f)  ∝  p_prior(f) · L(f | signals)

``L`` is a product of three interpretable factors (§2.3 of the build spec):

1. **Stated-price ceiling.** A seller cannot have a floor above the price they
   just offered, so grid points above it are crushed by ``CEILING_PENALTY``.
   Soft rather than hard, so a mis-parsed price can never zero out the belief.
2. **Gap model.** A stated price sits some gap ``g`` above the true floor. The
   expected gap grows when the seller concedes big and fast, and shrinks when
   they are firm. Language firmness also controls how *sharp* the inference is.
3. **Cheap talk.** Bluffing with no movement ("I have another buyer") applies
   only a whisper of tilt toward higher floors. The posterior visibly barely
   moves — that is the point, and the tilt is deliberately weak.

All three are computed in **log space** with a max-subtraction before
exponentiating. That is algebraically identical to the multiplicative form in
the spec but cannot underflow to an all-zero likelihood, which would otherwise
produce NaN on normalization when a stated price falls far from the grid.

Two deliberate extensions to the written spec, both to keep the math honest:

* **Repeated evidence is not double-counted.** If a seller restates a price they
  have already given (or moves *up*), the ceiling and gap factors are skipped —
  they were already applied when that price was new. Bayesian updating on the
  same evidence twice would spuriously sharpen the posterior. Cheap talk still
  applies, which is the correct treatment of "same number, more bluster".
* **Non-positive expected value is a walk.** If no feasible counter has positive
  expected surplus, the engine recommends WALK regardless of the ZOPA figure.

Decision layer
--------------
``recommend()`` maximizes expected surplus ``EV(o) = (V - o) · P(floor ≤ o)``
over offers that respect the negotiation's constraints (never bid down, never
exceed the configured ceiling, never concede more than
``MAX_CONCESSION_FRACTION`` of the remaining gap in one step).

R as a ceiling
--------------
Build spec §2.4 says offers must satisfy ``o <= R``, and §2.5 also expects the
final counter in ``[13,300, 13,800]`` with ``R = 13,000``. Those cannot both
hold. The contradiction traces to R itself: Phase 4 sets
``R = fair_value - hidden_costs``, netting repair costs out of *value*, while
``EV`` still scores surplus against the *gross* ``V``. Whether hidden costs
lower what the item is worth to you, or merely lower your target, is a product
decision — so it is a constructor argument rather than a buried assumption:

``offer_ceiling="R"`` (default)
    Spec-literal. Offers are capped at ``R`` and WALK triggers on
    ``P(floor ≤ R) < 0.25``. R is a hard economic limit: above it you are paying
    more than the item is worth to you net of repairs. On the demo listing
    (``asking 16,000, R 13,000``) this correctly walks on turn one, because a
    prior centred at ``0.88 × asking`` puts almost no mass under 13,000.

``offer_ceiling="V"``
    Offers may run up to fair value ``V``; WALK triggers on ``P(floor ≤ V)``.
    R stays the reported target that ``zopa()`` measures against. This is the
    reading that keeps the scripted demo alive with ``R = 13,000``.

Either way ``zopa()`` reports ``P(floor ≤ R)`` — the honest "are we going to hit
our number" figure — while ``recommend()["p_close"]`` reports the probability
against the ceiling actually being enforced.

Because ``P(floor ≤ o)`` is a right-continuous step function that jumps only at
grid points, ``EV`` is strictly decreasing between jumps. The maximizer is
therefore always at a grid point, or at the lower bound of the feasible
interval — so enumerating that finite candidate set is exact, not an
approximation. See ``_best_counter``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, NamedTuple

import numpy as np

# --------------------------------------------------------------------------
# Constants (§2.1, §2.3, §2.4 of the build spec). Tune here, nowhere else.
# --------------------------------------------------------------------------

# Grid & prior
GRID_LO_FRAC = 0.60          # grid spans [0.60·asking, 1.05·asking]
GRID_HI_FRAC = 1.05
GRID_POINTS = 61
PRIOR_MEAN_FRAC = 0.88       # truncated normal, mean 0.88·asking
PRIOR_STD_FRAC = 0.10        # std 0.10·asking

# Likelihood: stated-price ceiling
CEILING_PENALTY = 0.02       # multiplier on floors above the stated price

# Likelihood: gap model
GAP_CONCESSION_WEIGHT = 0.9  # how much of a concession we read as gap
GAP_SOFTNESS_FRAC = 0.06     # soft language widens the expected gap
GAP_MIN_FRAC = 0.01          # gap clipped to [0.01·asking, 0.18·asking]
GAP_MAX_FRAC = 0.18
SIGMA_BASE_FRAC = 0.05       # sigma_g = 0.05·asking·(1.5 - firmness)
SIGMA_FIRMNESS_OFFSET = 1.5
FINAL_CLAIM_SHARPENING = 0.6            # a *real* "final offer" spikes belief
FINAL_CLAIM_MIN_CONCESSION_FRAC = 0.01  # ...but only if backed by movement

# Likelihood: cheap talk
CHEAP_TALK_TILT = 0.04                  # deliberately weak — do not strengthen
CHEAP_TALK_MAX_CONCESSION_FRAC = 0.005  # above this it is not cheap talk

# Decision layer
WALK_ZOPA_THRESHOLD = 0.25   # below this probability of a deal, walk
MAX_CONCESSION_FRACTION = 0.40  # per-step cap on closing the remaining gap
FLOOR_BAND_QUANTILE = 0.10   # low edge of the reported ZOPA band

_TOL = 1e-9


class Action(str, Enum):
    """What Closer tells the user to do next. ``str`` mixin keeps it JSON-safe."""

    COUNTER = "COUNTER"
    HOLD = "HOLD"
    WALK = "WALK"
    ACCEPT = "ACCEPT"


# --------------------------------------------------------------------------
# Signals — the LLM's only job is to produce one of these per seller message
# --------------------------------------------------------------------------


@dataclass
class Signals:
    """Structured reading of a single seller message.

    Produced by ``app.llm.classify_seller_message``; consumed here. The engine
    never sees raw text, and the LLM never sees the belief distribution.
    """

    seller_price: float | None = None  # price stated in THIS message, else None
    concession_abs: float = 0.0        # prev_seller_price - seller_price, 0 if n/a
    firmness: float = 0.0              # 0..1, how firm/final the language is
    bluff_claim: bool = False          # "another buyer", "lots of interest"
    final_claim: bool = False          # "final offer", "lowest I'll go"
    walk_threat: bool = False          # seller threatens to end talks

    def __post_init__(self) -> None:
        if self.seller_price is not None:
            price = float(self.seller_price)
            if not math.isfinite(price):
                raise ValueError("seller_price must be finite")
            if price <= 0:
                raise ValueError("seller_price must be positive")
            self.seller_price = price

        concession = float(self.concession_abs)
        if not math.isfinite(concession):
            raise ValueError("concession_abs must be finite")
        self.concession_abs = concession

        firmness = float(self.firmness)
        if not math.isfinite(firmness):
            raise ValueError("firmness must be finite")
        # Clip rather than raise: an LLM occasionally returns 1.2, and a live
        # demo should degrade gracefully instead of 500-ing.
        self.firmness = min(1.0, max(0.0, firmness))

        self.bluff_claim = bool(self.bluff_claim)
        self.final_claim = bool(self.final_claim)
        self.walk_threat = bool(self.walk_threat)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Signals":
        """Build from loosely-typed JSON (the LLM layer's output)."""
        return cls(
            seller_price=payload.get("seller_price"),
            concession_abs=payload.get("concession_abs") or 0.0,
            firmness=payload.get("firmness") or 0.0,
            bluff_claim=bool(payload.get("bluff_claim", False)),
            final_claim=bool(payload.get("final_claim", False)),
            walk_threat=bool(payload.get("walk_threat", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seller_price": self.seller_price,
            "concession_abs": self.concession_abs,
            "firmness": self.firmness,
            "bluff_claim": self.bluff_claim,
            "final_claim": self.final_claim,
            "walk_threat": self.walk_threat,
        }

    #: Alias, so either spelling works at a call site.
    as_dict = to_dict


class Turn(NamedTuple):
    """One entry of the replay history: the signals and the posterior they produced."""

    signals: Signals
    posterior: np.ndarray


class Zopa(NamedTuple):
    """Zone of possible agreement: how likely a deal is, and over what band."""

    probability: float  # P(seller's floor <= R)
    low: float          # 10th percentile of the floor belief
    high: float         # the walk-away price R


# --------------------------------------------------------------------------
# BeliefState
# --------------------------------------------------------------------------


class BeliefState:
    """A belief distribution over the seller's hidden floor price.

    Parameters
    ----------
    asking:
        The listing price. Anchors the grid and every scale-relative constant.
    R:
        Walk-away price — the most the buyer will pay. From the expert payload.
    V:
        Expert fair value. Used as the value of the item when scoring surplus.
    """

    def __init__(
        self, asking: float, R: float, V: float, *, offer_ceiling: str = "R"
    ) -> None:
        self.asking = _positive_finite("asking", asking)
        self.R = _positive_finite("R", R)
        self.V = _positive_finite("V", V)

        # Which price is a hard ceiling on what we will offer, and the level the
        # WALK rule tests against. See the module docstring, "R as a ceiling".
        if offer_ceiling not in ("R", "V"):
            raise ValueError("offer_ceiling must be 'R' or 'V'")
        self.offer_ceiling = offer_ceiling
        self.ceiling: float = self.R if offer_ceiling == "R" else self.V

        self.floors: np.ndarray = np.linspace(
            GRID_LO_FRAC * self.asking, GRID_HI_FRAC * self.asking, GRID_POINTS
        )
        self.p: np.ndarray = self._build_prior()
        self.prior: np.ndarray = self.p.copy()
        self.history: list[Turn] = []

        # The listing price *is* the seller's opening quote. Seeding it here
        # makes the first counter's concession well-defined (16,000 -> 15,200 is
        # a real 800 move, not "n/a"), and makes a seller who merely restates
        # the asking price correctly register as no new information. Without
        # this the gap model reads an opening counter as near-final and the
        # belief pins ~500 too high, which walks every negotiation on turn one.
        self.last_seller_price: float | None = self.asking
        self.last_user_offer: float | None = None
        self._last_was_cheap_talk: bool = False

    # -- prior -------------------------------------------------------------

    def _build_prior(self) -> np.ndarray:
        """Truncated normal on the grid, normalized to sum to 1."""
        mean = PRIOR_MEAN_FRAC * self.asking
        std = PRIOR_STD_FRAC * self.asking
        log_pdf = -0.5 * ((self.floors - mean) / std) ** 2
        return _normalize_from_log(log_pdf)

    # -- update ------------------------------------------------------------

    def update(self, sig: Signals) -> "BeliefState":
        """Fold one seller message into the belief. Returns ``self`` for chaining."""
        if not isinstance(sig, Signals):
            raise TypeError("update() expects a Signals instance")

        log_l = self._log_likelihood(sig)
        posterior = _normalize_from_log(np.log(np.clip(self.p, 1e-300, None)) + log_l)

        if not np.all(np.isfinite(posterior)):  # pragma: no cover - defensive
            raise FloatingPointError("posterior became non-finite")

        self.p = posterior
        self.history.append(Turn(signals=sig, posterior=posterior.copy()))

        if sig.seller_price is not None:
            self.last_seller_price = sig.seller_price
        return self

    def _log_likelihood(self, sig: Signals) -> np.ndarray:
        """Log of L(f | signals), as the sum of the three factors in §2.3."""
        log_l = np.zeros_like(self.floors)
        stated = sig.seller_price is not None

        # Is this price genuinely new information about a *lower* floor? A
        # restated or raised price is evidence we have already folded in;
        # applying it again would double-count and spuriously sharpen.
        repeated = (
            stated
            and self.last_seller_price is not None
            and sig.seller_price >= self.last_seller_price - _TOL
        )
        new_price_info = stated and not repeated
        no_new_lower_price = (not stated) or repeated

        if new_price_info:
            # 1. Stated-price ceiling — the floor cannot exceed what they offered.
            log_l = log_l + np.where(
                self.floors > sig.seller_price, math.log(CEILING_PENALTY), 0.0
            )

            # 2. Gap model — the stated price sits some gap above the true floor.
            gap = float(
                np.clip(
                    GAP_CONCESSION_WEIGHT * sig.concession_abs
                    + (1.0 - sig.firmness) * GAP_SOFTNESS_FRAC * self.asking,
                    GAP_MIN_FRAC * self.asking,
                    GAP_MAX_FRAC * self.asking,
                )
            )
            sigma = SIGMA_BASE_FRAC * self.asking * (SIGMA_FIRMNESS_OFFSET - sig.firmness)
            if (
                sig.final_claim
                and sig.concession_abs > FINAL_CLAIM_MIN_CONCESSION_FRAC * self.asking
            ):
                # A "final offer" backed by real movement is credible: spike it.
                sigma *= FINAL_CLAIM_SHARPENING
            center = sig.seller_price - gap
            log_l = log_l - ((center - self.floors) ** 2) / (2.0 * sigma**2)

        # 3. Cheap talk — bluster with no movement barely moves the needle.
        if self._is_cheap_talk(sig, no_new_lower_price):
            spread = float(self.floors.std())
            tilt = 1.0 + CHEAP_TALK_TILT * (self.floors - self.floors.mean()) / spread
            log_l = log_l + np.log(np.clip(tilt, 1e-12, None))
            self._last_was_cheap_talk = True
        else:
            self._last_was_cheap_talk = False

        return log_l

    def _is_cheap_talk(self, sig: Signals, no_new_lower_price: bool) -> bool:
        return bool(
            sig.bluff_claim
            and sig.concession_abs < CHEAP_TALK_MAX_CONCESSION_FRAC * self.asking
            and no_new_lower_price
        )

    # -- summary statistics -------------------------------------------------

    def mean(self) -> float:
        return float(np.sum(self.p * self.floors))

    def std(self) -> float:
        mu = self.mean()
        return float(math.sqrt(max(0.0, np.sum(self.p * (self.floors - mu) ** 2))))

    def quantile(self, q: float) -> float:
        """Interpolated quantile of the floor belief.

        Uses the mass-centred CDF (``cumsum(p) - p/2``) so that a symmetric
        distribution returns its centre exactly, and interpolates linearly
        between support points rather than snapping to the 120-wide grid.
        """
        if not 0.0 <= q <= 1.0:
            raise ValueError("q must be in [0, 1]")
        support = self.p > 0
        if support.sum() == 1:
            return float(self.floors[support][0])
        cdf = (np.cumsum(self.p) - 0.5 * self.p)[support]
        values = self.floors[support]
        if q <= cdf[0]:
            return float(values[0])
        if q >= cdf[-1]:
            return float(values[-1])
        return float(np.interp(q, cdf, values))

    #: Alias — ``percentile`` reads better at call sites taking 0.10 / 0.50.
    percentile = quantile

    def median(self) -> float:
        return self.quantile(0.5)

    # -- decision layer -----------------------------------------------------

    def p_accept(self, offer: float) -> float:
        """P(seller's floor <= offer) — the CDF of the belief."""
        return float(self._p_accept_vec(np.asarray([offer], dtype=float))[0])

    def _p_accept_vec(self, offers: np.ndarray) -> np.ndarray:
        cum = np.cumsum(self.p)
        idx = np.searchsorted(self.floors, offers, side="right") - 1
        out = np.where(idx < 0, 0.0, cum[np.clip(idx, 0, len(cum) - 1)])
        # cumsum's last element can land a few ulps above 1.0.
        return np.clip(np.asarray(out, dtype=float), 0.0, 1.0)

    def zopa(self) -> Zopa:
        """Probability a deal exists at all, plus the band it likely sits in."""
        return Zopa(
            probability=self.p_accept(self.R),
            low=self.quantile(FLOOR_BAND_QUANTILE),
            high=self.R,
        )

    def record_user_offer(self, offer: float) -> float:
        """Record the buyer's standing offer. Monotone: never decreases."""
        value = _positive_finite("offer", offer)
        if self.last_user_offer is not None:
            value = max(value, self.last_user_offer)
        self.last_user_offer = value
        return value

    def _feasible_bounds(
        self, last_user_offer: float | None, last_seller_price: float | None
    ) -> tuple[float, float]:
        """The interval of offers we are allowed to make this turn."""
        if last_user_offer is None:
            lo = float(self.floors[0])
        else:
            lo = last_user_offer  # never bid against yourself downward

        hi = self.ceiling  # never offer above the configured ceiling
        if last_user_offer is not None and last_seller_price is not None:
            gap = last_seller_price - last_user_offer
            # Cap this step's concession at 40% of the remaining gap. A gap of
            # zero or less means they are already at or under us: don't move.
            step = MAX_CONCESSION_FRACTION * gap if gap > 0 else 0.0
            hi = min(hi, last_user_offer + step)
        return lo, hi

    def _best_counter(
        self, last_user_offer: float | None, last_seller_price: float | None
    ) -> tuple[float, float, float] | None:
        """Exact EV-maximizing offer, or None if no offer is feasible.

        ``EV(o) = (V - o)·P(floor <= o)``. ``P`` is constant between grid points
        and ``(V - o)`` strictly decreases, so ``EV`` strictly decreases between
        jumps: the maximizer is a grid point or the lower bound. Enumerating
        ``{lo} ∪ (grid ∩ [lo, hi])`` is therefore exhaustive, not a heuristic.
        """
        lo, hi = self._feasible_bounds(last_user_offer, last_seller_price)
        if hi < lo - _TOL:
            return None

        on_grid = self.floors[(self.floors >= lo - _TOL) & (self.floors <= hi + _TOL)]
        candidates = np.unique(np.concatenate(([lo], on_grid)))
        candidates = candidates[candidates <= hi + _TOL]
        if candidates.size == 0:  # pragma: no cover - lo always survives
            candidates = np.asarray([lo])

        probs = self._p_accept_vec(candidates)
        evs = (self.V - candidates) * probs
        best = int(np.argmax(evs))  # ties resolve to the cheapest offer
        return float(candidates[best]), float(evs[best]), float(probs[best])

    def recommend(
        self,
        *,
        last_user_offer: float | None = None,
        last_seller_price: float | None = None,
    ) -> dict[str, Any]:
        """The move to make right now, with every number needed to explain it.

        Precedence: ACCEPT > WALK > HOLD > COUNTER. ACCEPT outranks WALK because
        a live price at or below ``R`` is realized fact, whereas the ZOPA figure
        is only a prediction about the floor.
        """
        lu = self.last_user_offer if last_user_offer is None else float(last_user_offer)
        ls = (
            self.last_seller_price
            if last_seller_price is None
            else float(last_seller_price)
        )

        zone = self.zopa()
        counter = self._best_counter(lu, ls)
        # Probability a deal exists at or below the ceiling we actually enforce.
        # Identical to `zone.probability` under the default offer_ceiling="R".
        p_close = self.p_accept(self.ceiling)
        walk_ev = (self.V - self.ceiling) * p_close

        action: Action
        offer: float
        ev: float
        prob: float
        rationale: str

        if ls is not None and ls <= self.ceiling + _TOL and (
            counter is None or ls <= counter[0] + _TOL or (self.V - ls) >= counter[1]
        ):
            # Their price is inside our ceiling and beats holding out.
            action = Action.ACCEPT
            offer, prob, ev = ls, 1.0, self.V - ls
            rationale = (
                f"Their ${ls:,.0f} is at or under your ${self.ceiling:,.0f} ceiling and "
                f"beats the expected value of countering. Take it."
            )
        elif counter is None:
            action = Action.WALK
            offer, prob, ev = self.ceiling, p_close, walk_ev
            rationale = (
                f"No offer left that respects your ${self.ceiling:,.0f} ceiling. Walk."
            )
        elif p_close < WALK_ZOPA_THRESHOLD:
            action = Action.WALK
            offer, prob, ev = self.ceiling, p_close, walk_ev
            rationale = (
                f"Only a {p_close:.0%} chance their floor is at or under your "
                f"${self.ceiling:,.0f} ceiling. This deal probably isn't there."
            )
        elif counter[1] <= 0:
            action = Action.WALK
            offer, prob, ev = self.ceiling, p_close, counter[1]
            rationale = (
                f"No counter under ${self.ceiling:,.0f} has positive expected value. Walk."
            )
        elif self._last_was_cheap_talk and lu is not None:
            action = Action.HOLD
            offer = lu
            prob = self.p_accept(lu)
            ev = (self.V - lu) * prob
            rationale = (
                f"That was pressure, not movement — the math barely shifted. "
                f"Hold at ${lu:,.0f}."
            )
        elif lu is not None and abs(counter[0] - lu) <= _TOL:
            # The EV-optimal move is the number already on the table. Telling the
            # user to "counter" with their own standing offer would be nonsense.
            action = Action.HOLD
            offer, ev, prob = counter
            rationale = (
                f"You're already at the right number. Hold at ${offer:,.0f} — "
                f"~{prob:.0%} chance they take it, and their floor reads around "
                f"${self.median():,.0f}."
            )
        else:
            action = Action.COUNTER
            offer, ev, prob = counter
            rationale = (
                f"Counter ${offer:,.0f}: ~{prob:.0%} chance they take it, and their "
                f"floor reads around ${self.median():,.0f}."
            )

        return {
            "action": action.value,
            # Exact, unrounded — rounding here can push an offer a fraction of a
            # cent below the standing offer and break the monotonicity guarantee.
            # Formatting belongs to the message drafter and the dashboard.
            "offer": offer,
            "p_accept": prob,
            "ev": ev,
            "zopa": zone.probability,
            "zopa_low": zone.low,
            "zopa_high": zone.high,
            "floor_p10": zone.low,
            "p_close": p_close,
            "ceiling": self.ceiling,
            "floor_map": [float(x) for x in self.p],
            "floors": [float(x) for x in self.floors],
            "floor_point_est": self.median(),
            "floor_std": self.std(),
            "asking": self.asking,
            "R": self.R,
            "V": self.V,
            "last_seller_price": ls,
            "last_user_offer": lu,
            "turns": len(self.history),
            "rationale": rationale,
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _positive_finite(name: str, value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


def _normalize_from_log(log_weights: np.ndarray) -> np.ndarray:
    """exp-normalize in a way that cannot underflow to an all-zero vector."""
    shifted = log_weights - np.max(log_weights)
    weights = np.exp(shifted)
    total = weights.sum()
    if not math.isfinite(total) or total <= 0:  # pragma: no cover - defensive
        raise FloatingPointError("likelihood collapsed to zero mass")
    return weights / total


# --------------------------------------------------------------------------
# Scripted arc — `python -m app.engine` — for eyeballing calibration
# --------------------------------------------------------------------------

DEMO_ASKING = 16_000.0
DEMO_V = 14_200.0
DEMO_R = 13_000.0            # fair_value - hidden_costs, exactly as Phase 4 computes it
DEMO_OPENING_OFFER = 12_400.0

DEMO_ARC: list[tuple[str, Signals]] = [
    (
        "12.4 is way too low, this car's in great shape. I could do 15,200.",
        Signals(seller_price=15_200, concession_abs=800, firmness=0.7),
    ),
    (
        "I have someone coming to see it tomorrow.",
        Signals(seller_price=None, concession_abs=0, firmness=0.8, bluff_claim=True),
    ),
    (
        "You're killing me. 14,000 and it's yours, final.",
        Signals(
            seller_price=14_000, concession_abs=1_200, firmness=0.8, final_claim=True
        ),
    ),
]


def _print_arc(label: str, offer_ceiling: str) -> None:
    belief = BeliefState(
        asking=DEMO_ASKING, R=DEMO_R, V=DEMO_V, offer_ceiling=offer_ceiling
    )
    belief.record_user_offer(DEMO_OPENING_OFFER)

    print(f"\n{label}")
    print(
        f"  asking ${DEMO_ASKING:,.0f}   R ${DEMO_R:,.0f}   V ${DEMO_V:,.0f}"
        f"   ceiling ${belief.ceiling:,.0f}"
    )
    print(f"  {'turn':<5}{'median':>10}{'std':>9}{'zopa':>8}  action / offer")
    print(f"  {'-' * 62}")
    print(
        f"  {'prior':<5}{belief.median():>10,.0f}{belief.std():>9,.0f}"
        f"{belief.zopa().probability:>8.0%}  (user opened at ${DEMO_OPENING_OFFER:,.0f})"
    )

    for i, (text, signals) in enumerate(DEMO_ARC, start=1):
        belief.update(signals)
        rec = belief.recommend()
        if rec["action"] == Action.COUNTER.value:
            belief.record_user_offer(rec["offer"])
        print(f'  {"":<5}"{text}"')
        print(
            f"  {i:<5}{belief.median():>10,.0f}{belief.std():>9,.0f}"
            f"{rec['zopa']:>8.0%}  {rec['action']} ${rec['offer']:,.0f}"
            f"   (p_accept {rec['p_accept']:.0%}, EV ${rec['ev']:,.0f})"
        )
    print(f"  {'-' * 62}")
    print(f"  final: {belief.recommend()['rationale']}")


if __name__ == "__main__":  # pragma: no cover
    print("Closer engine \u2014 scripted seller arc, one R, two ceiling policies")
    _print_arc('[A] offer_ceiling="R"  (default, build spec \u00a72.4 literal)', "R")
    _print_arc('[B] offer_ceiling="V"  (offers may run up to fair value)', "V")
    print(
        "\nSame belief in both arcs \u2014 the ceiling is a decision-layer policy, not a"
        "\nmodel change. Arc A treats R as a hard economic limit and correctly walks:"
        "\na prior centred at 0.88\u00b7asking = $14,080 puts almost no mass under $13,000."
        "\nArc B lets offers run to fair value, which reproduces the \u00a77 demo narrative"
        "\nand lands the counter inside the \u00a72.5 band [13,300, 13,800].\n"
    )
