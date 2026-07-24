// ---------------------------------------------------------------------------
// Static content for the hackathon idea-selection dashboard.
// No backend: every value the UI renders lives in this typed module.
// ---------------------------------------------------------------------------

export type TrackId =
  | "technical"
  | "creative"
  | "linq"
  | "terac"
  | "dynamic"
  | "gametheory";

/** Fixed categorical color slot (1-6), assigned in palette order — never cycled. */
export type ColorSlot = 1 | 2 | 3 | 4 | 5 | 6;

export interface Track {
  id: TrackId;
  /** Short code used in dense contexts (matrix header, badges). */
  code: string;
  name: string;
  category: "General" | "Sponsor";
  prizeCashUsd: number;
  prizeRunnerUpUsd?: number;
  prizeExtraLabel?: string;
  prizeExtraUsd?: number;
  oneLiner: string;
  note?: string;
  colorSlot: ColorSlot;
}

export const TRACKS: Track[] = [
  {
    id: "technical",
    code: "TECH",
    name: "Most Technically Impressive",
    category: "General",
    prizeCashUsd: 1000,
    prizeExtraLabel: "Cursor credits",
    prizeExtraUsd: 1000,
    oneLiner: "Deepest, hardest engineering — the build that couldn't be faked.",
    note: "General track — must pick one general track",
    colorSlot: 1,
  },
  {
    id: "creative",
    code: "CREA",
    name: "Most Creative",
    category: "General",
    prizeCashUsd: 1000,
    prizeExtraLabel: "Cursor credits",
    prizeExtraUsd: 1000,
    oneLiner: "The idea nobody else in the room would have shipped.",
    note: "General track — must pick one general track",
    colorSlot: 2,
  },
  {
    id: "linq",
    code: "LINQ",
    name: "Best Use of Linq",
    category: "Sponsor",
    prizeCashUsd: 1000,
    prizeRunnerUpUsd: 500,
    oneLiner:
      "Real phone number on iMessage via API — interactive cards, Agent Pay, tapbacks, typing indicators, webhooks.",
    colorSlot: 3,
  },
  {
    id: "terac",
    code: "TERA",
    name: "Best Use of Terac",
    category: "Sponsor",
    prizeCashUsd: 1000,
    prizeRunnerUpUsd: 500,
    oneLiner:
      "Human labor on-demand via API/MCP ($250 team credit) — recruit real people mid-hackathon, prove measurable before→after.",
    colorSlot: 4,
  },
  {
    id: "dynamic",
    code: "DYNA",
    name: "Best Use of Dynamic",
    category: "Sponsor",
    prizeCashUsd: 750,
    prizeRunnerUpUsd: 250,
    oneLiner:
      "One SDK: auth + embedded non-custodial wallets + stablecoin payments + agent wallets, on Base Sepolia.",
    colorSlot: 5,
  },
  {
    id: "gametheory",
    code: "GAME",
    name: "Best Game Theory Project",
    category: "Sponsor",
    prizeCashUsd: 1000,
    oneLiner:
      "Nash equilibria, auctions, negotiation, multi-agent competition under imperfect information, bluff/tell detection.",
    colorSlot: 6,
  },
];

export const TRACKS_BY_ID: Record<TrackId, Track> = Object.fromEntries(
  TRACKS.map((t) => [t.id, t]),
) as Record<TrackId, Track>;

/** Total addressable prize money across every track (winner + runner-up + extras). */
export const TOTAL_PRIZE_POOL_USD = TRACKS.reduce(
  (sum, t) => sum + t.prizeCashUsd + (t.prizeRunnerUpUsd ?? 0) + (t.prizeExtraUsd ?? 0),
  0,
);

export interface WhyItWins {
  technical: string;
  creativity: string;
  functionality: string;
}

export interface BuildStep {
  phase: string;
  hours: number;
  description: string;
}

export interface Idea {
  id: string;
  /** 1 = top recommendation. Drives the emphasis treatment across every chart. */
  rank: number;
  name: string;
  tagline: string;
  tracksHit: TrackId[];
  prizePotentialUsd: number;
  effort: number; // 1-10
  impact: number; // 1-10
  demoRisk: number; // 1-10
  coreDemo: string;
  whyItWins: WhyItWins;
  stack: string[];
  buildPlan: BuildStep[];
  teracLoop: string | null;
}

export const IDEAS: Idea[] = [
  {
    id: "bubblebid",
    rank: 1,
    name: "BubbleBid",
    tagline: "Sealed-bid auctions that live inside an iMessage group chat.",
    tracksHit: ["linq", "gametheory", "dynamic", "technical"],
    prizePotentialUsd: 4750,
    effort: 8,
    impact: 9,
    demoRisk: 6,
    coreDemo:
      "Drop the agent into a 3-person group chat; it posts one iMessage App card auctioning an item; each person DMs a sealed bid; the card re-renders live (bids sealed → reveal → winner); Vickrey second-price logic computes the clearing price; the winner pays via Agent Pay / Dynamic wallet on Base Sepolia.",
    whyItWins: {
      technical:
        "Real-time card state machine over Linq webhooks + on-chain settlement + correct second-price auction math — nothing hard-codable.",
      creativity: "Messaging primitives as UI: a tapback becomes a confirm, a typing indicator means \"auction closing.\"",
      functionality: "Full loop, money in hand — bid to on-chain settlement, end to end.",
    },
    stack: ["Next.js API routes", "Linq API", "Dynamic SDK", "Postgres (Neon)"],
    buildPlan: [
      { phase: "Linq sandbox echo bot", hours: 2, description: "Stand up the Linq sandbox and get a bot echoing into a group thread." },
      { phase: "Auction state machine + Vickrey engine", hours: 3, description: "Sealed → reveal → winner state machine with tested second-price logic." },
      { phase: "iMessage App card renders", hours: 4, description: "Card UI that re-renders live inside the thread as bids arrive." },
      { phase: "Dynamic wallet settle on Sepolia", hours: 3, description: "Agent Pay checkout into a Dynamic wallet, settled on Base Sepolia." },
      { phase: "Polish + 2-min video", hours: 2, description: "Final pass and the submission video." },
    ],
    teracLoop: null,
  },
  {
    id: "mole-in-the-machine",
    rank: 2,
    name: "Mole in the Machine",
    tagline:
      "Social-deduction game played entirely in an iMessage group thread — 4 humans + 3 AI agents, one AI is the mole.",
    tracksHit: ["linq", "gametheory", "terac", "creative"],
    prizePotentialUsd: 4500,
    effort: 7,
    impact: 9,
    demoRisk: 5,
    coreDemo:
      "A live group chat where agents chat convincingly, humans vote via tapbacks, the mole runs a mixed-strategy deception policy, and an elimination card re-renders each round.",
    whyItWins: {
      technical: "Multi-agent orchestration with imperfect-information strategy on live messaging infra.",
      creativity: "The group thread as multiplayer lobby — the exact idea-starter judges seeded, executed to the max.",
      functionality: "Playable by judges on their own phones during the demo.",
    },
    stack: ["Node orchestrator", "Runware LLM agents", "Linq", "Terac MCP", "Redis"],
    buildPlan: [
      { phase: "Game engine + roles", hours: 3, description: "Core rules and role assignment, with tests." },
      { phase: "Linq group-thread I/O", hours: 3, description: "Wire the game engine to a live iMessage group thread." },
      { phase: "Agent personas + deception policy", hours: 3, description: "Give agents distinct voices and a mixed-strategy mole policy." },
      { phase: "Terac playtest + label round", hours: 2, description: "Recruit testers, run a round, collect labels." },
      { phase: "Tune + video", hours: 2, description: "Tune the mole persona from labels and record the submission video." },
    ],
    teracLoop:
      "Recruit ~30 general-population testers to play and label \"which player felt like AI / who was lying\"; use the labels to tune the mole's persona and show a before→after drop in detection rate.",
  },
  {
    id: "consensus-arena",
    rank: 3,
    name: "Consensus Arena",
    tagline: "A prediction market where AI agents with their own wallets trade against recruited humans.",
    tracksHit: ["dynamic", "terac", "gametheory", "technical"],
    prizePotentialUsd: 4250,
    effort: 8,
    impact: 8,
    demoRisk: 7,
    coreDemo:
      "Spin up 5 AI trader agents, each with a Dynamic agent wallet holding testnet USDC; an LMSR market maker prices questions (\"will X happen by 5pm?\"); Terac-recruited humans place opposing bets through the web app; a live price chart shows human-vs-AI capital flow; the market resolves and wallets settle on-chain.",
    whyItWins: {
      technical: "LMSR math + autonomous agent signing + real on-chain settlement.",
      creativity: "Humans vs. machines in a live market is a spectacle.",
      functionality: "Verifiable on-chain transactions, not a simulated ledger.",
    },
    stack: ["Next.js", "Dynamic agent wallets", "Base Sepolia", "Terac API", "LMSR engine (tested)"],
    buildPlan: [
      { phase: "LMSR engine", hours: 2, description: "Market-maker pricing engine with tests." },
      { phase: "Dynamic wallets + faucet funding", hours: 3, description: "Agent wallets provisioned and funded with testnet USDC." },
      { phase: "Trading UI + live chart", hours: 3, description: "Web app for humans to place opposing bets, with a live price chart." },
      { phase: "Agent trader policies", hours: 2, description: "Trading policies for the 5 AI agents." },
      { phase: "Terac human cohort + video", hours: 3, description: "Recruit the human cohort, run the market, record the video." },
    ],
    teracLoop:
      "Humans are counterparty liquidity and calibration data — recruited traders supply the human side of the human-vs-AI market.",
  },
  {
    id: "tell",
    rank: 4,
    name: "Tell",
    tagline: "Real-time negotiation copilot that detects bluffs and computes optimal counteroffers.",
    tracksHit: ["gametheory", "terac", "technical"],
    prizePotentialUsd: 3500,
    effort: 6,
    impact: 7,
    demoRisk: 4,
    coreDemo:
      "A two-party negotiation sim (salary / used car); the copilot ingests the transcript live, flags deception markers, models the opponent's reservation price as a Bayesian posterior, and recommends a counteroffer from the mixed-strategy equilibrium. Terac humans negotiate against the bot before/after tuning — a win-rate and surplus-captured chart proves improvement.",
    whyItWins: {
      technical: "Bayesian opponent modeling + equilibrium computation — measurably not hard-coded.",
      creativity: "A \"poker coach for real life.\"",
      functionality: "Judges can negotiate against it live.",
    },
    stack: ["Next.js", "Runware LLM API", "Terac", "Game-tree solver (tested)"],
    buildPlan: [
      { phase: "Negotiation model + solver", hours: 3, description: "Game model and equilibrium solver, with tests." },
      { phase: "Live transcript UI", hours: 2, description: "Real-time transcript ingestion and display." },
      { phase: "Deception-marker extraction", hours: 2, description: "Extract bluff/tell markers from the live transcript." },
      { phase: "Terac before/after study", hours: 3, description: "Recruit humans, measure win-rate and surplus before and after tuning." },
      { phase: "Video", hours: 1, description: "Record the submission video." },
    ],
    teracLoop:
      "Terac humans negotiate against the bot before/after tuning — a win-rate and surplus-captured chart proves the improvement.",
  },
  {
    id: "splitsquad",
    rank: 5,
    name: "SplitSquad",
    tagline: "One iMessage card that mutates plan → itinerary → split-the-bill checkout for a group night out.",
    tracksHit: ["linq", "dynamic", "creative"],
    prizePotentialUsd: 3750,
    effort: 5,
    impact: 6,
    demoRisk: 3,
    coreDemo:
      "A group chat picks dinner via tapback votes on one card; the card morphs into an itinerary; after dinner, a receipt photo becomes an itemized envy-free split (each person pays for what they consumed, proportional on shared items); Agent Pay checkout settles per person; a Dynamic wallet holds the pot.",
    whyItWins: {
      technical: "Card state machine + fair-division algorithm.",
      creativity: "A single-bubble UX arc that's memorable from vote to receipt.",
      functionality: "End-to-end money flow — lowest risk / safest ship of the five.",
    },
    stack: ["Next.js", "Linq", "Dynamic", "Receipt OCR via Runware vision"],
    buildPlan: [
      { phase: "Card flow state machine", hours: 3, description: "Plan → itinerary → checkout state machine." },
      { phase: "Tapback vote engine", hours: 2, description: "Group voting on the card via tapbacks." },
      { phase: "Receipt OCR + split algorithm", hours: 3, description: "Itemize the receipt and compute an envy-free split, with tests." },
      { phase: "Payments", hours: 2, description: "Agent Pay checkout into the Dynamic wallet pot." },
      { phase: "Video", hours: 1, description: "Record the submission video." },
    ],
    teracLoop: null,
  },
];

export const IDEAS_RANKED = [...IDEAS].sort((a, b) => a.rank - b.rank);

export const HACKATHON = {
  name: "YC Startup School Hackathon",
  location: "SF",
  dateLabel: "2026-07-24",
};

export const JUDGING_CRITERIA = [
  "Technical Impressiveness",
  "Creativity",
  "Functionality (+ social proof)",
] as const;

export const JUDGING_PENALTIES = [
  "Simple frontend / weak backend",
  "Hard-coded functionality",
  "Pre-existing projects",
] as const;

export const SUBMISSION_REQUIREMENTS = [
  "2-minute video",
  "Public repo",
  "Live URL recommended",
] as const;

export const RECOMMENDATION = {
  order: ["bubblebid", "mole-in-the-machine", "consensus-arena"] as const,
  rationale:
    "#1 BubbleBid carries the widest prize surface and the deepest technical build. #2 Mole in the Machine is the strongest Most Creative play. #3 Consensus Arena backs it up with a second Most Technically Impressive angle.",
};
