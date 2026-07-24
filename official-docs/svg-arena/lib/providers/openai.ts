import OpenAI from "openai";
import type { CompletionParams, CompletionResult, Provider } from "./types";

let client: OpenAI | null = null;
function getClient(): OpenAI {
  if (!client) {
    if (!process.env.OPENAI_API_KEY) {
      throw new Error("OPENAI_API_KEY is not set");
    }
    // Reasoning calls can be slow; cap each request and retry transient failures
    // so a single hung connection can't stall the whole batch run.
    client = new OpenAI({ timeout: 180_000, maxRetries: 3 });
  }
  return client;
}

export const openaiProvider: Provider = {
  name: "openai",
  async complete(params: CompletionParams): Promise<CompletionResult> {
    // GPT-5.x are reasoning models: send only model + messages. We deliberately
    // omit temperature / max_tokens — newer models reject them, and capping
    // output can starve the reasoning budget before any content is produced.
    // We steer entirely via the system/user prompt (same as the Anthropic side).
    const res = await getClient().chat.completions.create({
      model: params.modelId,
      messages: [
        { role: "system", content: params.system },
        { role: "user", content: params.user },
      ],
    });

    return {
      text: res.choices[0]?.message?.content ?? "",
      tokensIn: res.usage?.prompt_tokens ?? 0,
      tokensOut: res.usage?.completion_tokens ?? 0,
    };
  },
};
