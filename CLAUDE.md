# CLAUDE.md — hackathon-sf-001

## What we are doing

<!-- FILL IN when the idea locks -->
- **Project**: _TBD_
- **One-liner**: _TBD_
- **Target user**: _TBD_
- **Core demo (the thing judges see work)**: _TBD_
- **Stack**: _TBD_ (default lean: Next.js App Router, AI SDK v6 via Vercel AI Gateway, deploy on Vercel)

## Hackathon constraints

- **Deadline-driven.** Working demo beats perfect architecture. But "working" means actually working end-to-end, not faked.
- **Ship to a live URL.** Anything demoable should be deployable (Vercel preview) at any moment.
- **One clear happy path.** Nail the core flow before breadth.

## Working rules

- Real integrations over mocks. If we need a store/payments/auth/DB/email/AI, provision the real thing (Vercel Marketplace) — no UI-only stand-ins unless explicitly asked.
- Search before building. Reuse existing code and libs.
- Test the core path before calling it done.
- Keep a live URL green.

## Remember when implementing

The marginal cost of completeness is near zero with AI. Do the whole thing. Do it right. Do it with tests. Do it with documentation. Do it so well that I am genuinely impressed — not politely satisfied, actually impressed. Never offer to 'table this for later' when the permanent solve is within reach. Never leave a dangling thread when tying it off takes five more minutes. Never present a workaround when the real fix exists. The standard isn't 'good enough' — it's 'holy shit, that's done.' Search before building. Test before shipping. Ship the complete thing. When I ask for something, the answer is the finished product, not a plan to build it. Time is not an excuse. Fatigue is not an excuse. Complexity is not an excuse. Boil the ocean.
