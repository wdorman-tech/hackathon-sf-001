export interface CompletionResult {
  text: string;
  tokensIn: number;
  tokensOut: number;
}

export interface CompletionParams {
  modelId: string;
  system: string;
  user: string;
  maxTokens?: number;
  temperature?: number;
}

/**
 * Minimal provider interface. Adding OpenAI/Gemini/open-model hosts later means
 * implementing this once and registering it in providers/index.ts — no schema
 * or pipeline changes.
 */
export interface Provider {
  name: string;
  complete(params: CompletionParams): Promise<CompletionResult>;
}
