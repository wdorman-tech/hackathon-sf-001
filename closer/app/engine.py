"""Closer — the Bayesian negotiation engine.

PURE MATH. numpy only. This module must NEVER import httpx / anthropic / openai /
fastapi. The LLM (app.llm) translates a seller message into a `Signals` struct;
this file turns a sequence of Signals into a posterior belief over the seller's
hidden floor price and an optimal counter-offer. No LLM ever touches the numbers.

Interface contract (owned here, consumed by app.state / app.main):
    Signals                      — per-turn structured read of a seller message
    BeliefState(asking, R, V)    — holds the posterior `self.p` over `floors`
    BeliefState.update(sig)      — Bayesian update, one seller message
    BeliefState.recommend(...)   — decision layer → dict for the coach + chart

This is the spec-faithful REFERENCE implementation (build prompt §2). The tuned
numeric constants in `update()` are the one thing a teammate may refine in place;
the class/method signatures are the frozen contract the rest of the app builds on.

── A note on R vs V (resolves a spec inconsistency) ──────────────────────────
Build prompt §4 sets R = fair_value - hidden_costs = 13000, yet test #5 expects
the final counter in [13300, 13800] and the demo closes at 13500 — both ABOVE R.
So the optimizer cannot cap offers at R (that would cap at 13000). Coherent read:
  • V = fair value  = the most you'd rationally pay.
  • R = walk-away   = your target ceiling; Closer defends it and WALKs when a deal
                      at/below R looks impossible (P(floor <= R) < 0.25).
  • Counter-offers are optimized on [last_user_offer, V] — they may land between R
    and V (a good deal: under fair value, at-or-near walk-away).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

GRID_N = 61


@dataclass
class Signals:
    """Structured read of ONE seller message. Produced by app.llm.classify_*."""
    seller_price: Optional[float] = None   # price stated in THIS message, else None
    concession_abs: float = 0.0            # prev_seller_price - seller_price, 0 if n/a
    firmness: float = 0.5                  # 0..1, how firm/final the language is
    bluff_claim: bool = False              # "another buyer" etc. w/o real movement
    final_claim: bool = False              # "final offer", "lowest I'll go"
    walk_threat: bool = False              # seller threatens to end talks

    def as_dict(self) -> dict:
        return {
            "seller_price": self.seller_price,
            "concession_abs": self.concession_abs,
            "firmness": self.firmness,
            "bluff_claim": self.bluff_claim,
            "final_claim": self.final_claim,
            "walk_threat": self.walk_threat,
        }


class BeliefState:
    """Posterior over the seller's hidden floor price, updated message by message."""

    def __init__(self, asking: float, R: float, V: float):
        self.asking = float(asking)
        self.R = float(R)      # walk-away target
        self.V = float(V)      # expert fair value
        # Price grid over plausible seller floors.
        self.floors = np.linspace(0.60 * self.asking, 1.05 * self.asking, GRID_N)
        # Prior: truncated normal, mean 0.88*asking, std 0.10*asking, on the grid.
        mean, std = 0.88 * self.asking, 0.10 * self.asking
        prior = np.exp(-0.5 * ((self.floors - mean) / std) ** 2)
        self.p = prior / prior.sum()
        self.prior = self.p.copy()
        self.history: list[tuple[dict, np.ndarray]] = []
        self.last_signals: Optional[Signals] = None

    # ── Bayesian update ──────────────────────────────────────────────────────
    def update(self, sig: Signals) -> np.ndarray:
        """Multiply the posterior by a likelihood over the grid, renormalize."""
        floors, asking = self.floors, self.asking
        L = np.ones_like(self.p)

        # 1. Stated-price ceiling: the floor cannot exceed what they just offered.
        if sig.seller_price is not None:
            L[floors > sig.seller_price] *= 0.02

        # 2. Gap model (the core): stated price sits a gap above the true floor.
        #    Gap shrinks when firm & conceding little; grows on big/fast concession.
        if sig.seller_price is not None:
            g = np.clip(
                0.9 * sig.concession_abs + (1.0 - sig.firmness) * 0.06 * asking,
                0.01 * asking, 0.18 * asking,
            )
            # Wide on an ordinary counter (one anchor tells us little); sharp only
            # when the language is firm or a real "final" lands.
            sigma_g = 0.075 * asking * (1.5 - sig.firmness)
            if sig.final_claim and sig.concession_abs > 0.01 * asking:
                sigma_g *= 0.55  # a REAL "final" (with movement) spikes the belief
            sigma_g = max(sigma_g, 1e-6)
            L *= np.exp(-((sig.seller_price - g) - floors) ** 2 / (2.0 * sigma_g ** 2))

        # 3. Cheap talk: bluff with no real movement barely nudges the belief.
        if sig.bluff_claim and sig.concession_abs < 0.005 * asking:
            z = (floors - floors.mean()) / floors.std()
            L *= np.clip(1.0 + 0.04 * z, 1e-6, None)

        # 4. Renormalize; record history for the dashboard replay.
        self.p = self.p * L
        s = self.p.sum()
        self.p = self.p / s if s > 0 else self.prior.copy()
        self.last_signals = sig
        self.history.append((sig.as_dict(), self.p.copy()))
        return self.p

    # ── Posterior statistics ─────────────────────────────────────────────────
    def mean(self) -> float:
        return float((self.p * self.floors).sum())

    def std(self) -> float:
        m = self.mean()
        return float(np.sqrt((self.p * (self.floors - m) ** 2).sum()))

    def percentile(self, q: float) -> float:
        """Interpolated q-quantile (0..1) of the posterior over floors."""
        cdf = np.cumsum(self.p)
        return float(np.interp(q, cdf, self.floors))

    def median(self) -> float:
        return self.percentile(0.5)

    # ── Decision layer ───────────────────────────────────────────────────────
    def p_accept(self, offer: float) -> float:
        """P(seller accepts `offer`) = P(floor <= offer) = CDF of the belief."""
        return float(self.p[self.floors <= offer].sum())

    def zopa(self) -> float:
        """P(a deal exists at/below the walk-away R) = P(floor <= R)."""
        return float(self.p[self.floors <= self.R].sum())

    def _best_offer(self, last_user_offer: float,
                    last_seller_price: Optional[float]) -> tuple[float, float]:
        """argmax over legal offers of EV(o) = (V - o) * p_accept(o).

        Legal offers: monotone (>= last_user_offer), never above fair value V, and
        each concession capped at 40% of the remaining gap to the seller's price.
        """
        lo = last_user_offer
        hi = self.V
        if last_seller_price is not None and last_seller_price > lo:
            hi = min(hi, lo + 0.40 * (last_seller_price - lo))
        cand = self.floors[(self.floors >= lo) & (self.floors <= hi)]
        if cand.size == 0:
            cand = np.array([min(lo, self.V)])
        ev = (self.V - cand) * np.array([self.p_accept(o) for o in cand])
        i = int(np.argmax(ev))
        return float(cand[i]), float(ev[i])

    def recommend(self, last_user_offer: float,
                  last_seller_price: Optional[float] = None) -> dict:
        """Return the coach's move + everything the dashboard needs to draw."""
        best_offer, best_ev = self._best_offer(last_user_offer, last_seller_price)
        zopa = self.zopa()                                   # P(floor <= R): hit target
        p_fair = float(self.p[self.floors <= self.V].sum())  # P(floor <= V): closeable at all
        sig = self.last_signals

        bluff_no_move = bool(
            sig and sig.bluff_claim
            and sig.concession_abs < 0.005 * self.asking
            and (sig.seller_price is None or sig.seller_price >= last_user_offer)
        )

        action, offer = "COUNTER", best_offer
        if last_seller_price is not None and last_seller_price <= best_offer:
            # They already meet/beat what we'd counter — take it.
            action, offer = "ACCEPT", last_seller_price
        elif last_seller_price is not None and last_seller_price <= self.R \
                and (self.V - last_seller_price) > best_ev:
            # At/under walk-away and accepting beats the best counter's EV.
            action, offer = "ACCEPT", last_seller_price
        elif bluff_no_move:
            # Call the bluff: hold the current offer, make them come back.
            action, offer = "HOLD", last_user_offer
        elif p_fair < 0.25:
            # You'd most likely have to pay ABOVE fair value to close — walk.
            # (Gating on P(floor<=R) instead would walk on turn 1 of the demo, when
            #  the seller's opening anchor sits far above an aggressive R.)
            action, offer = "WALK", self.R

        return {
            "action": action,
            "offer": round(offer, 2),
            "p_accept": round(self.p_accept(offer), 4),
            "ev": round(best_ev, 2),
            "zopa": round(zopa, 4),
            "floor_point_est": round(self.median(), 2),
            "floor_p10": round(self.percentile(0.10), 2),
            "floor_std": round(self.std(), 2),
            "floor_map": {"floors": self.floors.round(2).tolist(),
                          "p": self.p.round(6).tolist()},
        }


# ── Eyeball harness: `python -m app.engine` prints the scripted demo arc ──────
def _demo_arc() -> None:
    asking, R, V = 16000, 13000, 14200
    b = BeliefState(asking, R, V)
    print(f"asking={asking}  R(walk-away)={R}  V(fair)={V}")
    print(f"{'turn':<34}{'median':>9}{'std':>8}{'zopa':>7}  recommendation")

    def show(label, rec):
        print(f"{label:<34}{rec['floor_point_est']:>9.0f}{rec['floor_std']:>8.0f}"
              f"{rec['zopa']:>7.2f}  {rec['action']} @ {rec['offer']:.0f} "
              f"(p_acc={rec['p_accept']:.2f})")

    print(f"{'PRIOR':<34}{b.median():>9.0f}{b.std():>8.0f}{b.zopa():>7.2f}")

    b.update(Signals(seller_price=15200, concession_abs=800, firmness=0.7))
    show("1) 'I could do 15,200'", b.recommend(last_user_offer=12400, last_seller_price=15200))

    b.update(Signals(seller_price=None, concession_abs=0.0, firmness=0.8, bluff_claim=True))
    show("2) 'another buyer' (bluff)", b.recommend(last_user_offer=13000, last_seller_price=15200))

    b.update(Signals(seller_price=14000, concession_abs=1200, firmness=0.5, final_claim=True))
    show("3) '14,000 final'", b.recommend(last_user_offer=13000, last_seller_price=14000))


if __name__ == "__main__":
    _demo_arc()
