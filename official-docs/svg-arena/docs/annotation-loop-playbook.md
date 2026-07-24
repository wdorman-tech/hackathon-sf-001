# The Annotation-Loop Playbook

**Audience:** anyone on the team (or any agent) standing up a human-in-the-loop model-improvement project on Terac.
**Goal:** make a model measurably better using human judgment we collect ourselves, and prove it with a before/after human eval.
**How to use this:** treat the Non-Negotiables as rules, the Runbook as the steps, and the Reference sections as defaults. Deviate only with a reason.

---

## The pattern (memorize this)

```
generate candidates  ->  humans judge them via Terac  ->  train / rerank  ->  held-out before/after on Terac
        ^                                                                              |
        +------------------------------ iterate -------------------------------------+
```

The environment you build is the cheap, disposable part. The scarce, valuable part is clean human signal collected fast. Optimize for signal, not for the app.

---

## Non-negotiables

Follow all of these unless you have a specific reason not to.

1. **Pick a layperson-judgeable quality axis.** Terac's panel is general population. They cannot grade code correctness or a medical claim. They can grade naturalness, clarity, helpfulness, persuasiveness, comprehension, and preference. Find the slice of your product's quality a smart layperson can judge, and improve that.
2. **Capture the Terac submission ID on every record.** This is mandatory. See the Submission-ID Standard below. Without it your data is anonymous and useless for dedupe, per-rater quality, and completion.
3. **Build calibration checks before your first launch.** No exceptions. They are the only reason anonymous paid data is trustworthy.
4. **Sign your pairings.** The client must never be trusted to report which option was correct or which two items it was shown.
5. **Store every judgment as an immutable row.** Never update or delete a vote. That table is the dataset.
6. **Rank with Bradley-Terry or raw head-to-head win rate. Never sequential Elo.** Elo is order-dependent and will hand you a top-ranked competitor with a losing record.
7. **Hold out a test set the training never sees.** Report your final number on it. This is what makes the result credible.
8. **Draft first; the draft is free and priced.** Read the quote before you ever launch. Launching is the only call that spends money.
9. **Pause the study the instant anything breaks.** Pausing is free and instant. Do not pay people to hit a broken page.
10. **On serverless, use an HTTP database driver, not a TCP connection pool.** Real concurrent annotator traffic will exhaust a pool and 500 your site.
11. **Sanitize untrusted model output before rendering it.** Anything the model generated is untrusted code.
12. **Reserve 30 to 40 percent of budget for the before/after eval.** That eval is the point. Do not spend it all collecting training data.

---

## Submission-ID Standard (the part people get wrong)

When Terac routes a participant to your task URL, it appends query params:

```
https://your-app.com/?submissionId=<id>&teracSubmissionId=<id>&taskId=<id>
```

That `submissionId` is the join key for everything. Capture it two ways, both:

**Client side**, on load, and persist it:
```js
const p = new URLSearchParams(location.search);
const submissionId = p.get("teracSubmissionId") ?? p.get("submissionId");
if (submissionId) localStorage.setItem("submissionId", submissionId);
// send it with every label you POST
```

**Server side**, as a fallback, off the Referer header (recovers sessions the client missed):
```js
const ref = new URL(req.headers.get("referer") ?? "");
const submissionId = body.submissionId
  ?? ref.searchParams.get("teracSubmissionId")
  ?? ref.searchParams.get("submissionId");
```

Store `submissionId` and `taskId` on every label row and every rater-session row. Do this on day one, before your first real launch.

---

## Terac MCP Runbook

1. **`terac_get_context`** first, always. Returns org, balance, and policies. If balance is 0, get credited before anything else.
2. **`terac_create_project`** to group the work.
3. **`terac_create_opportunity`** to build a DRAFT. Free, charges nothing, and returns a price quote. Template:
   ```jsonc
   {
     "title": "Pick the better output (5 min)",
     "project_id": "<from create_project>",
     "num_participants": 20,
     "business_type": "b2c",            // general population
     "tasks": [{
       "sequence": 1,
       "task_type": "activity",          // they visit your URL and do a task
       "review_type": "self_report",     // auto-approves and PAYS on completion
       "task_url": "https://your-app.com",
       "duration_minutes": 5
     }]
   }
   ```
4. Read `pricing.cost_per_participant_cents` from the response. Adjust and re-draft for free until the math is right.
5. **`terac_launch_draft_opportunity`** with the draft id. This spends money and starts recruiting.
6. Poll **`terac_get_submissions`** for per-person status and **`terac_get_opportunity`** for the lifecycle.
7. **`terac_pause_opportunity`** / **`terac_resume_opportunity`** to stop and restart recruiting instantly and for free.

Pricing reference (general-pop b2c, self-report activity): ~**$5.50** for a 5-minute task, ~**$16.50** for 30 minutes. You set duration; Terac sets the payout.

Lifecycle: `ACTIVE -> FULFILLED -> COMPLETED`. `FULFILLED` means the target was hit; it settles to `COMPLETED` on its own and cannot be stopped. `stop` is only valid from `ACTIVE` or `PAUSED`.

`self_report` auto-approves and pays on completion. You cannot withhold payment on your own quality signal, so quality control lives in your app (calibration), not in payment.

---

## Choose your annotation format

Do not default to A/B out of habit. Pick the format that produces the training signal you need.

| Format | Annotator does | Trains | Before/after metric |
|---|---|---|---|
| Pairwise (A/B) | picks the better of two | DPO / reward model | head-to-head win rate |
| Scalar / MOS (1-5) | rates one item | reward regression | mean-score lift |
| Multi-attribute rubric | scores several dimensions | multi-objective / targeted | per-axis lift |
| Best-of-N / ranking | picks top, or orders N | listwise reward / reranker | top-1 win rate |
| Span highlight | marks the flaw | targeted SFT / detector | flagged-spans down |
| Edit / correction | rewrites the output | SFT on human gold (strongest) | acceptance rate |
| Binary acceptance | ship it, yes/no | classifier / threshold | acceptance rate |
| Graded relevance | rates 0-3 | reranker | NDCG |
| Comprehension | reads output, answers a question | optimize for understanding | comprehension accuracy |

---

## Environment spec (minimum)

- One screen: the input, the candidate output(s), the response controls, optional reason tags. Reason tags are cheap and tell you why you lost; always include them.
- Generate all model outputs offline and store them. The live app only reads.
- Immutable label rows. Suggested columns: `id, prompt_id, item_a_id, item_b_id, response, reason_tags, rater_session, terac_submission_id, terac_task_id, is_calibration, calibration_passed, created_at`.
- A rater-session row per browser: `token, terac_submission_id, vote_count, calibration_passed, calibration_failed, quality_score`.
- HTTP DB driver. Sanitize outputs. Capture submission IDs (above).

---

## Quality-control standard

- ~12% of items are calibration checks: an obviously-correct option vs an obviously-broken one.
- Sign the pairing so the client cannot tell or flip which side is correct. Recommended token payload, HMAC'd and verified with a constant-time compare:
  ```
  { promptId, leftId, rightId, isCheck, correctSide, ts }
  ```
- Per rater, track passed/failed and set `quality_score = passed / (passed + failed)`.
- In analysis, down-weight or drop anyone whose quality is low (e.g. fails more checks than they pass).
- Always report results **twice**: raw, and quality-weighted. If they agree, your result is real.

---

## Budget discipline

- At ~$5.50 per 5-minute session, a typical credit goes a long way; a 5-minute session is ~20+ judgments.
- Favor **more people doing shorter tasks** over a few doing long ones. You are buying taste diversity, not volume from one person.
- Split the budget: most of it on collecting/iterating, **30 to 40 percent reserved for the held-out before/after eval**.

---

## Turning labels into a better model

- Pairwise -> filter to high-confidence pairs (unanimous or strong margin), drop ties, run **DPO** (LoRA on a small open model is the fast path).
- If the base can barely do the task, **SFT on the winners first**, then DPO.
- Edit/correction format -> **SFT on the human-corrected gold**. Strongest signal available.
- Short on time -> train a small **reward model** and do **best-of-N reranking** at inference, no fine-tune required.
- Optional leverage: calibrate an **LLM judge** against a gold human set (report agreement), then use the judge to scale labels. Humans are the anchor, the judge is the volume.

---

## The before/after eval (the deliverable)

1. On held-out prompts the training never saw, generate outputs from the **base** model and the **improved** model.
2. Put them head-to-head in the arena, blind, and launch a fresh Terac round.
3. Report the improved-vs-base **win rate** (Bradley-Terry or raw), raw and quality-weighted.

"Our model beat the base 63% of the time across 400 human judgments on held-out prompts" is the bar. Anything less grounded is a proxy.

---

## Good to know when integrating

- **URL params are undocumented.** Expect to discover them; capture them anyway (above).
- **Submission payloads are thin** (id + status). Get per-rater work counts from your own DB via the submission ID.
- **No payment gating on `self_report`.** Quality control is yours; calibration handles it.
- **No completion webhooks.** Poll `get_submissions`.
- **`FULFILLED` is undocumented and unstoppable.** Plan for `ACTIVE -> FULFILLED -> COMPLETED`.
- **Pricing is set by duration**, not directly. Draft to discover it.
- **Pin your Node version for training/generation scripts** (tooling like tsx breaks on old Node). Use the up-to-date runtime explicitly.

---

## Definition of done

- [ ] Submission IDs captured on every record (client + Referer).
- [ ] Calibration checks live, signed, and feeding a per-rater quality score.
- [ ] Immutable label store; outputs sanitized; HTTP DB driver.
- [ ] At least one full iteration: collect -> train/rerank -> retest.
- [ ] Held-out test set never used in training.
- [ ] Before/after win rate reported, raw and quality-weighted.
- [ ] Ranking computed with Bradley-Terry or win rate, not Elo.
- [ ] Budget reserved and spent on the final eval.
