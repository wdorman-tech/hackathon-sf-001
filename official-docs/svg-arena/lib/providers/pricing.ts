/**
 * Per-1M-token pricing (USD) for cost estimates. Only models with a known
 * published price are listed; anything else yields a null cost (we don't
 * fabricate prices). Update as pricing changes / models are added.
 */
const PRICING: Record<string, { in: number; out: number }> = {
  // Anthropic
  "claude-opus-4-8": { in: 5, out: 25 },
  "claude-sonnet-4-6": { in: 3, out: 15 },
  "claude-haiku-4-5": { in: 1, out: 5 },
  // OpenAI prices intentionally omitted until verified → cost recorded as null.
};

export function estimateCostUsd(
  modelId: string,
  tokensIn: number,
  tokensOut: number,
): number | null {
  const p = PRICING[modelId];
  if (!p) return null;
  return (tokensIn * p.in + tokensOut * p.out) / 1_000_000;
}
