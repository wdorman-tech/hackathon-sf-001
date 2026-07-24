# DEMO.md — the runbook

Closer is a phone number, not a URL. **+1 (205) 261-1117.**

Two processes have to be alive for it to answer: the backend, and
`linq webhooks listen`. If either dies the number goes quiet with **no error
anywhere** — that is the single failure this runbook is built around.

---

## T-30 minutes

```bash
cd ~/Desktop/hackathon-sf-001
make kill          # a stale backend on :8000 answers /health with linq:false and looks fine
make dev           # backend + supervised listener, both restart on crash
```

In a second terminal:

```bash
make preflight     # six checks; all must be green
```

`make preflight` checks, cheapest first, each one a thing that has actually
broken: backend up → keys loaded → store is durable → **listener alive** →
`linq` profile is the closer line → real round trip. The last one needs a phone
that has already texted us (Shared Line is inbound-first):

```bash
PREFLIGHT_TO=+1XXXXXXXXXX make preflight
```

Then seed the second deal so multi-deal has something to show:

```bash
make seed          # a 2016 Civic to switch to
```

**Do not skip `make check-profile`.** `~/.linq/config.json` holds one active
profile shared by every process on the machine. `linq profile use seller` in any
other terminal silently repoints us, and the demo texts from the seller's
number. `make dev` runs the check for you and refuses to boot if it fails.

---

## Before you speak

- Phone mirrored to the screen, Messages open on the thread with **+12052611117**.
- Do Not Disturb **on**. Notifications on a mirrored phone are a live grenade.
- Screen brightness up, auto-lock **Never**.
- `caffeinate -dimsu make dev` if the laptop has ever slept on you.
- A terminal visible somewhere with `make inbound` ready to run.

---

## The arc — 2008 Camry LE, listed $6,400

Marcus is the seller agent (`~/seller-agent`, port 8787, +1 205 490 9563).
He anchors, concedes in shrinking steps, quotes retail comps while deflecting
KBB, and claims other interested buyers when there are none.

Send these from the demo phone, in order. Times are cumulative.

| # | You send | What appears | Say this |
|---|---|---|---|
| 0:00 | the listing link | typing indicator, then the research card — fair value, hidden costs, red flags, **with sources** | "It's reading the listing and pulling comps. Those citations are real URLs it fetched." |
| 0:40 | `He said: it's 6,400 and honestly it's worth more than that. I've had a lot of interest.` | COUNTER ≈ $4,848, floor ≈ $5,600 ± 577 | "It's not guessing. That's a probability distribution over the lowest number he'd actually take." |
| 1:10 | `He said: tell you what, 6,000 for a quick sale.` | floor tightens to ≈ $5,474 ± 266. **Says WALK** — his floor still reads above your $4,750 ceiling | "He moved $400 and the belief narrowed by half. Right now it's telling me to be ready to leave — his floor is still above what the car is worth." |
| **1:40** | **`He said: I've got two other people coming to see it Saturday.`** | **floor ≈ $5,478 — moves $3.52** | **"That's the whole product. He applied pressure with no number behind it, and the math moved three dollars and fifty-two cents. It called the bluff."** |
| 2:10 | `He said: 5,600 and that's me being generous.` | COUNTER ≈ $5,040 | "Now he's actually moving, and it moves with him." |
| 2:30 | `He said: fine. 5,000, final offer, I'm not going lower.` | ACCEPT $5,000, deal likely 82% | "Under fair value. Take it." |
| 2:50 | `deal` | confetti, closed card, savings | "$1,360 under ask." |
| 3:05 | `deals` | numbered list, two deals | "It runs more than one negotiation." |
| 3:15 | `2` | switches, shows that deal's card | "One character to switch context." |

**The line that matters is 1:40.** Everything before it is setup and everything
after it is proof. If you are running long, cut 2:10 — never cut 1:40.

Dry-run the whole thing with no phone at all:

```bash
make demo          # drives the same arc through /simulate
```

---

## The three recoveries

Rehearse all three in Sync 2. Each is one command and a sentence you say out loud
while you run it — narrating the recovery is better than pretending nothing
happened.

### 1. The number stops answering

**Symptom:** you text it and nothing comes back. No error anywhere.

```bash
make inbound       # seconds_since_last_event climbing past 300 => listener is dead
```

`scripts/listen.sh` is already restarting it with backoff, so wait five seconds
and send again. If it stays dead:

```bash
# in the make dev terminal: Ctrl-C, then
make dev
```

> "The listener process died — it's supervised, so it's already coming back."

### 2. Research hangs or the listing 403s

**Symptom:** the research card doesn't arrive within ~40 seconds.

The wall-clock cap means it will always return *something* by 40s. If the
listing itself was refused and no price was parsed, Closer asks
*"what are they asking?"* — answer with a bare number and it recomputes.

If the network is gone entirely:

```bash
# Ctrl-C the dev terminal, then
RESEARCH_MODE=mock make dev
```

Mock is instant, needs no network, and has a canned payload for both demo cars
(Camry and CX-5), matched off the listing URL.

> "Dropping to cached research so we're not waiting on the venue wifi."

### 3. The PNG card doesn't render

**Symptom:** `card` returns nothing, or an error.

The Unicode card is the fallback and always works — it shipped first for exactly
this reason. Nothing to do but say so:

> "That's the text version of the same card."

---

## Numbers worth knowing cold

| | |
|---|---|
| Closer's number | **+1 (205) 261-1117** |
| Marcus (seller agent) | +1 205 490 9563, port 8787 |
| Listing / fair value / walk-away | $6,400 / $5,200 / $4,750 |
| Close | ~$5,000, **$1,360 under ask** |
| The bluff move | **$3.52** on the floor estimate ($5,474.42 → $5,477.94) |
| Belief grid | 61 points over 60–105% of asking |
| Engine tests | 204 |

---

## If a judge asks

**"How do you know it isn't just an LLM guessing?"**
The LLM never sees a number. It turns the seller's sentence into six structured
signals — price, concession size, firmness, bluff, final-offer, walk-threat —
and a numpy Bayesian update does the rest. `closer/app/engine.py` imports numpy
and nothing else. 204 tests, including a differential test against an
independent reimplementation of the update rule.

**"What happens if it's wrong about the floor?"**
It's a distribution, not a point. The card shows the spread, and the
recommendation maximizes expected surplus against the whole curve — so a wide
belief automatically produces a more conservative counter.

**"Could I use this?"**
Text the number. That is the entire signup flow — no app, no account. (Shared
Line caps us at 20 contacts, so this is real but not infinite.)

---

## Hand the phone over

The strongest possible close is a judge texting it themselves.

```bash
linq contacts add +1XXXXXXXXXX --profile closer
```

That prints a `shareLink` — put its QR on the final slide. On a phone it opens
Messages with a pre-filled draft; the judge just hits send.
