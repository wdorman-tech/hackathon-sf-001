import Anthropic from "@anthropic-ai/sdk";
import type { CompletionParams, CompletionResult, Provider } from "./types";

let client: Anthropic | null = null;
function getClient(): Anthropic {
  if (!client) {
    if (!process.env.ANTHROPIC_API_KEY) {
      throw new Error("ANTHROPIC_API_KEY is not set");
    }
    client = new Anthropic();
  }
  return client;
}

export const anthropicProvider: Provider = {
  name: "anthropic",
  async complete(params: CompletionParams): Promise<CompletionResult> {
    // Stream so large SVG outputs don't hit the SDK's HTTP timeout. Adaptive
    // thinking + high effort improves illustration quality. No sampling params
    // (temperature etc.) — they 400 on Opus 4.8 and we steer via the prompt.
    const stream = getClient().messages.stream({
      model: params.modelId,
      max_tokens: params.maxTokens ?? 32000,
      system: params.system,
      thinking: { type: "adaptive" },
      output_config: { effort: "high" },
      messages: [{ role: "user", content: params.user }],
    });

    const message = await stream.finalMessage();
    const text = message.content
      .filter((b): b is Anthropic.TextBlock => b.type === "text")
      .map((b) => b.text)
      .join("");

    return {
      text,
      tokensIn: message.usage.input_tokens,
      tokensOut: message.usage.output_tokens,
    };
  },
};
