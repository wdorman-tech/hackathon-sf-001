import type { Provider } from "./types";
import { anthropicProvider } from "./anthropic";
import { openaiProvider } from "./openai";

const PROVIDERS: Record<string, Provider> = {
  anthropic: anthropicProvider,
  openai: openaiProvider,
};

export function getProvider(name: string): Provider {
  const p = PROVIDERS[name];
  if (!p) throw new Error(`Unknown provider: ${name}`);
  return p;
}

export type { Provider, CompletionParams, CompletionResult } from "./types";
export { estimateCostUsd } from "./pricing";
