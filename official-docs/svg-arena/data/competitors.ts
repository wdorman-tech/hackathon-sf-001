/**
 * PROMPT-EVOLUTION EXPERIMENT — model fixed to GPT-5-mini, only the system
 * prompt varies. config.systemPrompt is the genome; config.version / parent
 * track lineage. Human votes in the arena rank prompt versions.
 *
 * ROUND 2 (Generation 1) roster:
 *  - mini-p0-baseline  : Gen-0 champion (unchanged — keeps its existing SVGs)
 *  - mini-p1-fidelity  : Gen-1 challenger, bred from baseline by hardening the
 *                        universal weakness from Gen 0 ("more accurate to prompt")
 *                        plus detail (minimal-flat lost on too little detail).
 *  - gpt55-benchmark   : FIXED anchor — GPT-5.5 with a naive/default prompt.
 *                        The "Goliath" line: can an evolved mini prompt beat the
 *                        flagship used without prompt engineering?
 * The Gen-0 losers (minimal-flat, rich-dimensional) are dropped from the active
 * roster (seed deactivates anything not listed); their data is preserved.
 */
export interface CompetitorSeed {
  key: string;
  name: string;
  provider: string;
  modelId: string;
  technique: "zero_shot" | "best_of_n" | "self_critique";
  config: Record<string, unknown>;
}

const HARD_RULES = `Output ONLY a single valid, self-contained <svg>...</svg> element — no markdown fences, no commentary before or after. Always include a viewBox; design on a 512x512 canvas unless the prompt implies another aspect ratio. Never reference external resources (no external images, fonts, scripts, or hyperlinks). The SVG must render correctly on its own in any modern browser.`;

// Gen-0 champion — DO NOT EDIT this text (must match the SVGs already in the DB).
const PROMPT_V0_BASELINE = `You are a world-class SVG illustrator and visual designer. You produce polished, detailed, aesthetically refined illustrations purely as SVG code.

${HARD_RULES}

Use clean vector shapes, gradients, and a thoughtful, cohesive color palette. Aim for strong composition, correct proportions, depth, and visual polish.`;

// Gen-2 challenger — Round 2 showed the BOLD "structured+rich" rework LOST to
// baseline (over-decoration cost accuracy + cleanliness). So Gen 2 breeds from
// the baseline champion and goes SURGICAL on the persistent universal gradient
// — "more accurate to prompt" — while explicitly avoiding the clutter that sank
// v1. Accuracy + clean composition over busyness.
const PROMPT_V2_ACCURACY = `You are a world-class SVG illustrator and visual designer. You produce polished, accurate, and clean illustrations purely as SVG code.

${HARD_RULES}

Your #1 priority is ACCURACY TO THE PROMPT. Before drawing, note every object, attribute, count, and spatial relationship the prompt names, and make sure each is clearly and correctly depicted — the right number of items, the right colors, the right arrangement, nothing missing or substituted.

Then keep it CLEAN: a correct, well-composed, uncluttered image beats a busy one. Do NOT add unrequested elements, filler, or decoration that could distract or introduce errors. Use a cohesive color palette, correct proportions, a clear focal point, sensible depth, and keep every shape crisp and free of glitches or overlaps.`;

// Fixed benchmark — GPT-5.5 with a naive, unengineered prompt (what someone
// would write with zero prompt effort). This is the "flagship, untuned" anchor.
const PROMPT_BENCHMARK_NAIVE = `You generate SVG images. Output a single SVG that illustrates the user's request. Respond with only the SVG code, nothing else.`;

export const COMPETITORS: CompetitorSeed[] = [
  {
    key: "mini-p0-baseline",
    name: "Prompt v0 · baseline",
    provider: "openai",
    modelId: "gpt-5-mini",
    technique: "zero_shot",
    config: { systemPrompt: PROMPT_V0_BASELINE, version: 0, parent: null },
  },
  {
    key: "mini-p2-accuracy",
    name: "Prompt v2 · accuracy+clean",
    provider: "openai",
    modelId: "gpt-5-mini",
    technique: "zero_shot",
    config: { systemPrompt: PROMPT_V2_ACCURACY, version: 2, parent: "mini-p0-baseline" },
  },
  {
    key: "gpt55-benchmark",
    name: "GPT-5.5 (naive prompt) — benchmark",
    provider: "openai",
    modelId: "gpt-5.5",
    technique: "zero_shot",
    config: { systemPrompt: PROMPT_BENCHMARK_NAIVE, version: 0, parent: null, benchmark: true },
  },
];
