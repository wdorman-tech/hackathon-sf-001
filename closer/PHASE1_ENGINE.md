# Phase 1 — the Bayesian negotiation engine

`app/engine.py` + `tests/test_engine.py`. Pure numpy, zero network calls, 204 tests.

This is the piece the Game Theory track is judged on. The claim it has to survive is
*"the math is real"* — so no LLM ever touches a number. The LLM turns a seller's
message into a `Signals` struct on the way in and prose on the way out; everything
between is deterministic and inspectable.

---

## Quick start

```bash
cd closer
python -m venv .venv && .venv/bin/pip install numpy pytest
.venv/bin/python -m pytest tests/ -q       # 204 passed
.venv/bin/python -m app.engine             # prints the scripted demo arc
```

The engine needs only `numpy`; `pytest` is test-only. No API keys, no `.env`, no network.

---

## The model

The seller has a hidden reservation price `f` — the lowest number they'd actually
accept. We hold a belief `p(f)` over a 61-point price grid spanning
`[0.60 × asking, 1.05 × asking]`, start from a truncated normal centred at
`0.88 × asking` (std `0.10 × asking`), and multiply in a likelihood per message:

```
p_posterior(f)  ∝  p_prior(f) · L(f | signals)
```

`L` is a product of three interpretable factors:

| Factor | What it encodes |
|---|---|
| **Stated-price ceiling** | They can't have a floor above the price they just named. Grid points above it are crushed by `0.02` — soft, so a mis-parsed price can never zero the belief. |
| **Gap model** | A stated price sits some gap `g` above the true floor. `g` grows when they concede big and fast, shrinks when they're firm. Firmness also sets how *sharp* the inference is; a "final offer" backed by real movement narrows it further. |
| **Cheap talk** | Bluffing with no movement ("I've got another buyer") applies a whisper of tilt — the tilt spans `[0.92, 1.08]` and the posterior visibly barely moves. That's the demo beat. Do not strengthen it. |

Decision layer: maximize expected surplus `EV(o) = (V − o) · P(floor ≤ o)` over
offers that never bid down, never exceed the ceiling, and never concede more than
40% of the remaining gap in one step.

---

## API

```python
from app.engine import BeliefState, Signals, Action

belief = BeliefState(asking=16_000, R=13_000, V=14_200)   # offer_ceiling="R" by default
belief.record_user_offer(12_400)

belief.update(Signals(seller_price=15_200, concession_abs=800, firmness=0.7))
rec = belief.recommend()

rec["action"]           # "COUNTER" | "HOLD" | "WALK" | "ACCEPT"
rec["offer"]            # exact float — format at the presentation layer
rec["floor_point_est"]  # posterior median: "their floor reads around $X"
rec["rationale"]        # one-line plain-English explanation
```

### `BeliefState(asking, R, V, *, offer_ceiling="R")`

| Arg | Meaning |
|---|---|
| `asking` | Listing price. Anchors the grid and every scale-relative constant. |
| `R` | Walk-away price. Phase 4 computes `fair_value − sum(hidden_costs)`. |
| `V` | Fair value. The value side of the surplus `(V − o)`. |
| `offer_ceiling` | `"R"` or `"V"` — see [The R-vs-V decision](#the-r-vs-v-decision). |

**Methods.** `update(sig)` (returns `self`, chainable) · `recommend(*, last_user_offer=None,
last_seller_price=None)` · `record_user_offer(offer)` (monotone; never decreases) ·
`mean()` · `std()` · `median()` · `quantile(q)` / `percentile(q)` · `p_accept(offer)` ·
`zopa()`.

**State.** `p` (posterior, sums to 1) · `floors` (the grid) · `prior` (turn-0 snapshot) ·
`history` (list of `Turn(signals, posterior)` for dashboard replay) · `last_seller_price` ·
`last_user_offer`.

### `Signals` — the LLM's entire output surface

```python
Signals(
    seller_price   = 15_200,   # price stated in THIS message, None if none
    concession_abs = 800,      # prev_seller_price − seller_price
    firmness       = 0.7,      # 0..1, how firm/final the language is
    bluff_claim    = False,    # "another buyer", "lots of interest"
    final_claim    = False,    # "final offer", "lowest I'll go"
    walk_threat    = False,    # threatens to end talks
)
```

`Signals.from_dict(payload)` builds from loose JSON; `.to_dict()` / `.as_dict()` go back.
Invalid input raises (`NaN`, non-positive price); out-of-range `firmness` is **clipped**,
not rejected, so a model returning `1.2` degrades instead of 500-ing mid-demo.

### `recommend()` payload

`action` · `offer` · `p_accept` · `ev` · `zopa` · `zopa_low` · `zopa_high` · `floor_p10` ·
`p_close` · `ceiling` · `floor_map` (list, parallel to `floors`) · `floors` ·
`floor_point_est` · `floor_std` · `asking` · `R` · `V` · `last_seller_price` ·
`last_user_offer` · `turns` · `rationale`.

JSON-serializable as-is — `floor_map` and `floors` are plain lists, `action` is a string.

**Action precedence:** `ACCEPT > WALK > HOLD > COUNTER`. ACCEPT outranks WALK because a
live price at or under the ceiling is realized fact, whereas ZOPA is a prediction.
`offer` is returned **unrounded** — rounding to cents can push it a fraction below the
standing offer and break the monotonicity guarantee. Format at the presentation layer.

---

## The R-vs-V decision

Build spec §2.4 says offers must satisfy `o ≤ R`. §2.5 also expects the final counter in
`[13,300, 13,800]` with `R = 13,000`. **Those cannot both hold.**

The contradiction traces to R itself: Phase 4 sets `R = fair_value − hidden_costs`, netting
repair costs out of *value*, while `EV` still scores surplus against the *gross* `V`.
Whether hidden costs lower what the item is worth to you, or merely lower your target, is a
product decision — so it's a constructor argument, not a buried assumption. Run
`python -m app.engine` to see both, same R, same belief:

| | `offer_ceiling="R"` (default) | `offer_ceiling="V"` |
|---|---|---|
| turn 1 · "I could do 15,200" | **WALK** $13,000 | COUNTER $13,440 |
| turn 2 · bluff, no movement | WALK $13,000 | **HOLD** $13,440 |
| turn 3 · "14,000, final" | COUNTER $12,960 | HOLD $13,440 · 93% |
| §2.5 band `[13,300, 13,800]` | not reachable | ✅ $13,440 |

**`"R"` is spec-literal and economically strict** — above R you're paying more than the item
is worth to you net of repairs, so walking is correct. On the demo listing it walks on turn
one, because a prior centred at `0.88 × asking = $14,080` puts almost no mass under $13,000.

**`"V"` reproduces the §7 demo narrative** with the spec's own `R = 13,000`, no re-tuning.
`zopa()` still reports `P(floor ≤ R)` — the honest "will we hit our number" figure — while
`p_close` reports the probability against the ceiling actually enforced.

The ceiling is a **decision-layer policy only**; the posterior is byte-identical under both
(`test_ceiling_mode_does_not_change_the_belief`).

> **Recommendation:** ship the demo with `offer_ceiling="V"`, and revisit whether Phase 4
> should subtract the full hidden costs from R at all. A timing-belt service is partly
> priced into "fair market value" already, so subtracting all of it arguably double-counts.

---

## It is not car-specific

Every constant is a fraction of `asking`, so the engine only ever sees ratios. Same arc
shape across five verticals, all tested:

```
laptop      $900      → $776      (13.8% under ask)
motorcycle  $4,200    → $3,560    (15.2% under)
used car    $16,000   → $13,440   (16.0% under)
house       $625,000  → $525,000  (16.0% under)
ticket      $320      → $271      (15.3% under)
```

`test_a_laptop_and_a_house_negotiate_identically` multiplies every price by 1,000 and
asserts the normalized belief is **bit-identical**, the action matches, and offers scale
exactly. Scale invariance is exact, not approximate.

What actually drives the outcome is **`R / asking`**, not the item. The prior sits at
`0.88`, so a walk-away below ~`0.85 × asking` fights it from turn one — which is exactly why
the spec's `R = 13,000` (`0.813 ×`) walks. A test sweeps `R/asking` from 0.78 to 0.94 across
all five verticals and confirms ZOPA rises monotonically.

**WALK is a signal, not a terminal state.** The house scenario walks on turn 1 and recovers
to COUNTER on turn 3 when the seller concedes. Phase 3's state machine must **not**
transition to `DONE(walked)` on a WALK recommendation alone — wait for the user to confirm.

---

## Tests

```
tests/test_engine.py — 204 passed in 0.33s
```

| Group | # | Covers |
|---|---|---|
| `TestCrossVertical` | 22 | Laptop → house; exact scale invariance |
| `TestSignals` | 18 | LLM output validation: NaN, negatives, clipping, coercion |
| `TestAgainstReferenceImplementation` | 17 | Math vs. the spec formula and Gaussian conjugacy |
| `TestEdgeCases` | 17 | Determinism, replay, no-mutation, 10 → 1e9 price scales |
| `TestOfferCeiling` | 13 | Both R/V policies, incl. §2.5 band at the spec's R |
| `TestOptimizer` | 13 | Offer bounds, concession cap, exact EV-optimality |
| `TestGridAndPrior`, `TestConstructorValidation`, `TestUpdateInvariants`, `TestActionSelection` | 11 ea | Prior shape, bad-input rejection, normalization, action selection |
| `TestGapModel` | 10 | Concessions move mass down; firmness sharpens |
| `TestCheapTalk` | 9 | Bluffs barely move; no double-counting |
| `TestPAcceptAndZopa`, `TestQuantiles` | 8 / 7 | CDF monotonicity, interpolated median |
| `TestRecommendPayload` | 6 | JSON-serializable, every key the dashboard needs |
| `TestScriptedArc*` | 8 | Build spec §2.5, both walk-away readings |
| `TestFuzz` | 2 | 300 random arcs + a 200-turn conversation |
| `TestNamingAffordances` | 3 | `percentile` alias, `floor_p10` key |

Three mechanisms carry the weight:

**Differential testing.** `_reference_posterior()` re-implements §2.3 the naive way — plain
multiplication, no log space. 14 parametrized cases assert the engine matches to `rtol=1e-10`,
so the numerically-stable rewrite is *proven* identical to the spec, not assumed. A separate
test checks the posterior against the closed-form Gaussian precision-weighted mean.

**Exhaustive optimality.** `test_offer_is_exactly_ev_optimal` brute-forces 20,001 offers and
asserts the engine is never beaten. The engine evaluates ~10 candidates, because `EV` is
provably maximized at a grid point (`P` is a step function, `(V − o)` strictly decreasing);
the test confirms that proof empirically.

**Fuzzing.** 300 seeded random negotiations with hostile inputs — out-of-range firmness,
negative concessions, prices from `0.3×` to `1.4×` asking — asserting invariants after every
turn. This caught two float bugs: ZOPA reaching `1.0000000000000004`, and `round(offer, 2)`
pushing an offer a fraction of a cent below the standing offer.

---

## Design decisions worth knowing

**The asking price seeds the seller's opening quote.** `last_seller_price` starts at
`asking`, so the first counter (16,000 → 15,200) is a real $800 move rather than "n/a".
Without this the gap model reads an opening counter as near-final, the belief pins ~$460 too
high, and *every* negotiation walks on turn one.

**Repeated evidence is not double-counted.** A restated or raised price skips the ceiling and
gap factors — they were applied when that number was new. Bayesian updating on the same fact
twice would spuriously sharpen the posterior and break the bluff beat. Cheap talk still
applies, which is the right read of "same number, more bluster". Consequence: a price *above*
the last one is inert. That's deliberate — going up is hardball, not evidence of a lower floor.

**The likelihood is computed in log space** with max-subtraction. Algebraically identical to
§2.3, but it cannot underflow to an all-zero likelihood and NaN the belief. Prior mass below
`1e-300` is floored rather than zeroed, which also lets a belief recover if the seller does
something that contradicts everything so far.

**Quantiles use the mass-centred CDF** (`cumsum(p) − p/2`) and interpolate over the support,
so a symmetric belief returns its centre exactly and the median isn't biased half a grid cell.

**`walk_threat` is collected but unused.** §2.3 and §2.4 never consume it. There's a test
pinning that as documented behaviour so nobody assumes otherwise — it's the obvious next
signal to wire in.

---

## Integration notes

This branch is standalone Phase 1 — my code only, no dependency on other branches. The
interface differs from the reference scaffold on `main` in a few places; if you integrate,
these are the deltas:

| Reference (`main`) | Here |
|---|---|
| `update(sig)` → `ndarray` | → `self` (chainable). Read `belief.p`. |
| `recommend(last_user_offer, last_seller_price)` positional | keyword-only, both optional — the engine tracks them |
| `zopa()` → `float` | → `Zopa(probability, low, high)`. The `"zopa"` **payload key is still a float**. |
| `floor_map: {"floors": [...], "p": [...]}` | two top-level keys, `floors` and `floor_map` |
| `Signals.as_dict()` | both `as_dict()` and `to_dict()` |
| `percentile(q)` | both `percentile(q)` and `quantile(q)` |

Everything else — constructor signature, `p`, `floors`, `prior`, `history`, `p_accept`,
`mean`, `std`, `median`, and the `action` / `offer` / `p_accept` / `ev` / `zopa` /
`floor_point_est` / `floor_p10` / `floor_std` payload keys — matches.
