import { getProvider, estimateCostUsd } from "./providers";
import { sanitizeSvg } from "./svg";

export interface Competitor {
  provider: string;
  modelId: string;
  technique: string;
  config: Record<string, unknown>;
}

export interface GenerationResult {
  status: "ok" | "error";
  svg: string | null; // sanitized, browser-safe
  svgRaw: string | null; // model's original output
  tokensIn: number;
  tokensOut: number;
  latencyMs: number;
  costUsd: number | null;
  meta: Record<string, unknown>;
  error?: string;
}

const SYSTEM_PROMPT = `You are a world-class SVG illustrator and visual designer. You produce polished, detailed, aesthetically refined illustrations purely as SVG code.

Rules:
- Output ONLY a single valid, self-contained <svg>...</svg> element. No markdown code fences, no commentary, no explanation before or after.
- Always include a viewBox. Design on a 512x512 canvas unless the prompt clearly implies another aspect ratio.
- Use clean vector shapes, gradients, and a thoughtful, cohesive color palette. Aim for strong composition, correct proportions, depth, and visual polish.
- Never reference external resources (no external images, fonts, scripts, or hyperlinks).
- The SVG must render correctly on its own in any modern browser.`;

function userPrompt(prompt: string): string {
  return `Create a high-quality SVG illustration of the following:\n\n${prompt}`;
}

/** Generate one SVG for a competitor + prompt, applying its technique. */
export async function generate(
  competitor: Competitor,
  prompt: string,
): Promise<GenerationResult> {
  const start = Date.now();
  const provider = getProvider(competitor.provider);
  let tokensIn = 0;
  let tokensOut = 0;
  const meta: Record<string, unknown> = { technique: competitor.technique };

  // A competitor may carry its own system prompt (this is how prompt-version
  // experiments work: same model, different system prompt). Falls back to the
  // shared default.
  const system =
    (typeof competitor.config.systemPrompt === "string" &&
      competitor.config.systemPrompt) ||
    SYSTEM_PROMPT;

  try {
    let rawSvg: string;

    if (competitor.technique === "best_of_n") {
      const n = Number(competitor.config.n ?? 3);
      const candidates: string[] = [];
      for (let i = 0; i < n; i++) {
        const r = await provider.complete({
          modelId: competitor.modelId,
          system,
          user: userPrompt(prompt),
        });
        tokensIn += r.tokensIn;
        tokensOut += r.tokensOut;
        candidates.push(r.text);
      }
      const chosen = await selectBest(competitor, prompt, candidates);
      tokensIn += chosen.tokensIn;
      tokensOut += chosen.tokensOut;
      rawSvg = candidates[chosen.index] ?? candidates[0];
      meta.candidateCount = n;
      meta.chosenIndex = chosen.index;
    } else if (competitor.technique === "self_critique") {
      const first = await provider.complete({
        modelId: competitor.modelId,
        system,
        user: userPrompt(prompt),
      });
      tokensIn += first.tokensIn;
      tokensOut += first.tokensOut;

      const revised = await provider.complete({
        modelId: competitor.modelId,
        system,
        user: `You previously produced this SVG for the prompt "${prompt}":\n\n${first.text}\n\nCritique it for flaws — proportions, composition, color, prompt adherence, and any rendering problems — then produce an improved version. Output ONLY the improved <svg> element.`,
      });
      tokensIn += revised.tokensIn;
      tokensOut += revised.tokensOut;
      rawSvg = revised.text;
      meta.revised = true;
    } else {
      // zero_shot (default)
      const r = await provider.complete({
        modelId: competitor.modelId,
        system,
        user: userPrompt(prompt),
      });
      tokensIn += r.tokensIn;
      tokensOut += r.tokensOut;
      rawSvg = r.text;
    }

    const svg = sanitizeSvg(rawSvg);
    return {
      status: svg ? "ok" : "error",
      svg,
      svgRaw: rawSvg,
      tokensIn,
      tokensOut,
      latencyMs: Date.now() - start,
      costUsd: estimateCostUsd(competitor.modelId, tokensIn, tokensOut),
      meta,
      error: svg ? undefined : "No valid SVG found in model output",
    };
  } catch (err) {
    return {
      status: "error",
      svg: null,
      svgRaw: null,
      tokensIn,
      tokensOut,
      latencyMs: Date.now() - start,
      costUsd: estimateCostUsd(competitor.modelId, tokensIn, tokensOut),
      meta,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/** Ask the model to pick the best of N candidate SVGs. Falls back to index 0. */
async function selectBest(
  competitor: Competitor,
  prompt: string,
  candidates: string[],
): Promise<{ index: number; tokensIn: number; tokensOut: number }> {
  const provider = getProvider(competitor.provider);
  const list = candidates
    .map((c, i) => `### Candidate ${i}\n${c}`)
    .join("\n\n");
  const r = await provider.complete({
    modelId: competitor.modelId,
    system:
      "You are an expert art director judging SVG illustrations. Reply with ONLY the integer index of the single best candidate — nothing else.",
    user: `Prompt: "${prompt}"\n\nPick the candidate that best matches the prompt and has the highest visual quality.\n\n${list}\n\nBest candidate index:`,
    maxTokens: 16,
  });
  const match = r.text.match(/\d+/);
  let index = match ? parseInt(match[0], 10) : 0;
  if (!Number.isInteger(index) || index < 0 || index >= candidates.length) {
    index = 0;
  }
  return { index, tokensIn: r.tokensIn, tokensOut: r.tokensOut };
}
