/** Shared arena constants used by both the API and the UI. */

export const WINNERS = ["a", "b", "tie", "both_bad"] as const;
export type Winner = (typeof WINNERS)[number];

export const REASON_TAGS = [
  "Better composition",
  "More accurate to prompt",
  "Cleaner shapes",
  "Fewer glitches",
  "Better color",
  "More detailed",
] as const;

/** Probability that a served pair is an attention check (quality control). */
export const ATTENTION_CHECK_RATE = 0.12;

/** A deliberately poor SVG used as the wrong answer in an attention check. */
export const DUD_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#d4d4d4"/><rect x="220" y="236" width="72" height="40" fill="#9ca3af"/></svg>`;

/** The payload we sign and hand to the client with each served pair. */
export interface PairToken {
  promptId: number;
  leftGenId: number; // -1 if the left side is the dud (attention check)
  rightGenId: number; // -1 if the right side is the dud
  check: boolean; // is this an attention check?
  correct?: "a" | "b"; // for checks: which side is the real (correct) SVG
  ts: number;
}
