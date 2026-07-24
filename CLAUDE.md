# CLAUDE.md — hackathon-sf-001

## What we are doing

<!-- FILL IN when the idea locks -->
- **Project**: _TBD_
- **One-liner**: _TBD_
- **Target user**: _TBD_
- **Core demo (the thing judges see work)**: _TBD_
- **Stack**: _TBD_ (default lean: Next.js App Router, Runware for all AI inference, deploy on Vercel)

## Hackathon constraints

- **Deadline-driven.** Working demo beats perfect architecture. But "working" means actually working end-to-end, not faked.
- **Ship to a live URL.** Anything demoable should be deployable (Vercel preview) at any moment.
- **One clear happy path.** Nail the core flow before breadth.

## The other half of the demo lives outside this repo

`~/seller-agent` holds **Marcus**, a private-party car seller agent on its own
Linq account. He is the counterparty Closer negotiates against: a 2008 Camry LE
listed at $6,400 that is honestly worth about $4,200, with a $4,750 walk-away he
never states. He anchors, concedes in shrinking steps, quotes retail listing
comps while deflecting KBB, and claims other interested buyers when there are
none — which is exactly the `bluff_claim` signal `closer/app/engine.py` is built
to detect.

Two Linq accounts, one per agent, so they can text each other:

| | Closer (here) | Marcus (`~/seller-agent`) |
|---|---|---|
| Number | +12052611117 | +12054909563 |
| CLI profile | `closer` | `seller` |
| Port | 8000 | 8787 |

**Every `linq` command here needs `--profile closer`.** See `LINQ.md`.

## Runware task API — shape rules that bite

Verified against the live API (July 2026). Getting these wrong returns a 400,
not a degraded response:

- `messages[].role` accepts only `user` / `assistant` / `tool`. A `system`
  message must be lifted into `settings.systemPrompt` (`invalidMessageRole`).
- `maxTokens` and `temperature` live under `settings`, not at the top level
  (`unsupportedParameter`). Full allowed set: `maxTokens`, `temperature`,
  `topP`, `topK`, `systemPrompt`, `stopSequences`, `thinkingLevel`,
  `splitThinking`, `presencePenalty`, `frequencyPenalty`, `repetitionPenalty`,
  `minP`, `search`.
- `taskUUID` must be a real UUIDv4.
- `jsonSchema` + `outputFormat: "json"` did **not** reliably constrain output on
  `anthropic:claude@sonnet-4.6` — it still returned prose in a code fence. Parse
  defensively rather than trusting the schema.

`closer/app/runware.py` handles the first two centrally, so callers can keep
writing ordinary OpenAI-style message lists.

## Working rules

- Real integrations over mocks. If we need a store/payments/auth/DB/email, provision the real thing (Vercel Marketplace) — no UI-only stand-ins unless explicitly asked.
- **All AI inference goes through Runware** — text, vision, image, video, audio, 3D, one endpoint (`POST https://api.runware.ai/v1`, `Authorization: Bearer $RUNWARE_API_KEY`). Models are AIR ids, `creator:family@version` (e.g. `anthropic:claude@sonnet-4.6`); browse https://runware.ai/models. Native task API for anything with image inputs or JSON-schema output; the OpenAI-compatible `/v1/chat/completions` shim is text-only. Credits: https://runware.ai/wallet, code `YCSSHACKATHON`. No direct provider SDKs (`anthropic`, `openai`, `google-genai`) unless Runware genuinely can't do it.
- Search before building. Reuse existing code and libs.
- Test the core path before calling it done.
- Keep a live URL green.

## Remember when implementing

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to 'table this for later' when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't 'good enough' — it's 'holy shit, that's done.' Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.
