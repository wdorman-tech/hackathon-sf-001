# Tracks

#### ‣ Track Information

You can apply to multiple tracks, but must ***choose one General Track*** (Most Creative or Technically Impressive).

The top 2 teams for ***Most Creative*** and ***Most Technically Impressive*** will be called up for live demos (4 teams total).

A winning project is one that brings technical novelty and creativity to solve an interesting problem. 

Projects will be scored based on **Technical Impressiveness**, **Creativity**, and **Functionality****.** Social proof (traction with users or social media) is also considered.

Judging rubrics will not be shared.

We advise against:

- Simple frontends with lackluster backends
- Projects with hard-coded functionality (judges will check)
- Submitting a pre-existing startup/project (see project requirements at bottom)
We encourage you to:

- Use AI coding tools ***heavily*** to build fast
- Be as creative as possible!

#### ‣ Compute Credits

- [**Runware**](https://runware.ai/) is providing $35 in compute credits per person [**here**](https://runware.ai/wallet)** **(code **YCSSHACKATHON)**. If you have questions, the team will be available on [**Discord**](https://discord.gg/7xckzEPxbN) and [**Email**](mailto:alasdair.nicoll@runware.ai).
- Cursor has provided $50 in credits for all registered hackers.

### ‣ General Tracks ($2,000)

**Most Technically Impressive: $1,000 + $1k Cursor Credits**

**Most Creative: $1,000 + $1k Cursor Credits**

---

### ‣  Best Use of Linq ($1,500)

Linq gives your agent a ***real phone number*** on*** iMessage*** — iMessage, RCS and SMS from one API, plus Payments, iMessage Apps, rich media, Find My location, effects, reactions, typing indicators, read receipts, and webhooks on every event. The part most people don't know about: iMessage Apps, an interactive card that renders inside iMessage — a game board redraws after a move, an order flips from "Reserved" to "Confirmed" in the familiar blue bubble. And with Agent Pay, checkout happens right there: the payment card opens an Apple Pay App Clip, and the money settles to your own Stripe account.

**To setup, follow these instructions:**

1. Go to [https://linqapp.com/cli](https://linqapp.com/cli) (can copy agent instructions)
1. Sign up for free sandbox account
  - NOTE: must have recipient text your Linq sandbox number first
1. Make sure to apply best practices: [https://docs.linqapp.com/getting-started/best-practices/](https://docs.linqapp.com/getting-started/best-practices/)
1. Let us know of any questions or if you run into any issues!
Idea starter: iMessage Apps. Put your agent in a group chat and let one card carry an entire flow — a plan that mutates into an itinerary that mutates into a split-the-bill checkout, all in the same bubble. The best projects will treat messaging primitives as UI: a 👍 tapback is a vote, a typing indicator is a loading state, a group thread is your multiplayer lobby.

**First Place: $1,000**

**Runner-Up: $500**

‣ **Resources: **[*API Documentation*](https://docs.linqapp.com/getting-started/quickstart/)

---

### ‣  Best Use of Terac ($1,500)  

Terac is an expert network powering frontier research: human labor on-demand via API. Tell us the job and expertise needed, and we handle sourcing, screening, verification, and payouts. Raised $9M (Emergence, SignalFire, Audacious, Z Fellows). 

Most hackathon projects never meet a real user before the demo. This track is different: use real human input you collect during the hackathon to make your project measurably better, whether that's product feedback, user testing, expert judgment, or labeled data.

1. **Build something real people can respond to.** An app people can use, react to, label, rate, rank, or compare.
1. **Call the Terac API/MCP to bring the people.** We handle recruiting and incentives.
1. **Turn that input into a better project.** Show a clear before and after.
**To setup, follow these steps:**

- [Sign in](https://terac.com/researchers/login) to Terac as a researcher. Slack us for team credits.
- **$250 Terac credit** per team.
- General-population participants only (no specialist panels).
- [[Set up MCP](https://terac.com/mcp)] / [[API docs](https://terac.com/docs/developers)]
**First Place: $1,000**

**Runner-Up: $500**

‣ **Resources: **[*MCP Documentation*](https://terac.com/mcp)**; **[*API Documentation*](https://terac.com/docs/developers)**; **[*Example Project 1*](https://github.com/TeracAI/svg-arena)*; *[*Example Project 2*](https://github.com/TeracAI/svg-arena/blob/main/docs/annotation-loop-playbook.md)

### ‣ Best Use of Dynamic ($1,000)  

Dynamic is wallet infrastructure: one SDK that combines login, embedded wallets, key management, signing, and stablecoin payments. Instead of stitching together an auth provider, wallet connectors, and a signing stack, you integrate Dynamic and get all of it. 

Users sign in with email or social, no seed phrases, no extensions, and get a non-custodial embedded wallet automatically. From there they can send, receive, and pay in stablecoins with sub-second signing. And with agent wallets, you can give an AI agent its own wallet to hold funds and sign transactions autonomously. 

The best projects will go beyond a basic integration. Show us a creative use of Dynamic (wallets, money movement, or agent wallets).To set up:

1. Create an environment at [app.dynamic.xyz](https://app.dynamic.xyz/). Grab your environment ID.
1. Install the Dynamic MCP. This gives your AI coding agent live access to our full docs. [One-click for Cursor](https://cursor.com/en/install-mcp?name=dynamic&config=eyJ1cmwiOiJodHRwczovL3d3dy5keW5hbWljLnh5ei9kb2NzL21jcCJ9), or `claude mcp add --transport http dynamic `[`https://www.dynamic.xyz/docs/mcp`](https://www.dynamic.xyz/docs/mcp) for Claude Code.
1. Use prompt your agent! Flush out your idea and stack, and let it build.
1. We recommend building on Base Sepolia (testnet) so there's no real money at risk. Get testnet USDC from the [Circle faucet](https://faucet.circle.com/) and gas ETH from a [Base Sepolia faucet](https://docs.base.org/base-chain/network-information/network-faucets).
1. No crypto experience needed. Dynamic handles the hard parts.
**First Place: $750**

**Runner-Up: $250**

‣ **Resources:***** ***[*Hackathon Landing Page*](https://www.dynamic.xyz/docs/overview/dynamic-yc-startup-school-hackathon)*;*[* *](https://www.dynamic.xyz/docs/overview/introduction/welcome)[*Example Repos*](https://github.com/dynamic-labs-oss/examples)*;*[* *](https://github.com/matthew1809/dynamic-agent-payments-starter)[*Agent Payments Starter*](https://github.com/matthew1809/dynamic-agent-payments-starter)*;*[* *](https://www.dynamic.dev/)[*Live Demo Apps*](https://www.dynamic.dev/)

### ♠️ Best Game Theory Project ($1,000)  

The best strategic problems reduce to the same core challenge: incomplete information, competing incentives, and figuring out the optimal move when you can't see your opponent's hand.

This track rewards projects that apply **game theory** to any domain: Nash equilibria, mixed strategies, auctions, negotiation, multi-agent competition, and beyond.

**Idea starters:**

- An auction or negotiation agent that computes optimal bidding strategy in real time
- A multi-agent simulator where bots compete/cooperate under imperfect information
- A tool that detects bluffing, deception, or "tells" in text, voice, or behavior (fraud, security, dating apps, negotiations)
- A matching-market or resource-allocation system that models strategic behavior of participants
**First Place: $1,000**

### ‣ Project Requirements

- Projects must be built during the hackathon. Pre-existing startups or projects will not be allowed. Building on top of an existing product is allowed, but only the new feature will be evaluated - it must stand on its own merit.
- Functionality should be real - that means you should not hard-code the core functionality of your product.
- Your team will submit:
  - A recorded demo as a Youtube link (**2 minutes MAX)**
  - A Github repo (**must be public**)
  - (recommended) A live deployment link

### ‣ SUBMIT PROJECT HERE

- (link will be posted soon)
