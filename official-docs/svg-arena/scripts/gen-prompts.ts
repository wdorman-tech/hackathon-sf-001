import { config } from "dotenv";
config({ path: ".env.local" });
config({ path: ".env" });

import OpenAI from "openai";
import { db, schema } from "../lib/db";
import { CATEGORY_LABELS, type Category } from "../data/prompts";

// How many new prompts to request per category (default 8).
const PER_CATEGORY = Number(process.env.PROMPTS_PER_CATEGORY ?? 8);
// Model used to author prompts — cheap + fast is fine here.
const MODEL = process.env.PROMPT_MODEL ?? "gpt-5-mini";

const client = new OpenAI({ timeout: 120_000, maxRetries: 3 });

function parseList(text: string): string[] {
  // Prefer a JSON array; fall back to line-by-line.
  const match = text.match(/\[[\s\S]*\]/);
  if (match) {
    try {
      const arr = JSON.parse(match[0]);
      if (Array.isArray(arr)) return arr.map(String);
    } catch {
      /* fall through */
    }
  }
  return text
    .split("\n")
    .map((l) => l.replace(/^\s*[-*\d.)\]]+\s*/, "").trim())
    .filter(Boolean);
}

async function promptsForCategory(category: Category): Promise<string[]> {
  const label = CATEGORY_LABELS[category];
  const res = await client.chat.completions.create({
    model: MODEL,
    messages: [
      {
        role: "system",
        content:
          "You write concise, concrete prompts for AI SVG illustration benchmarks. Each prompt is a single vivid subject suitable for a standalone illustration. Vary subjects widely; avoid near-duplicates. Return ONLY a JSON array of strings, no prose.",
      },
      {
        role: "user",
        content: `Category: ${label}. Write ${PER_CATEGORY} distinct illustration prompts that fit this category. Each 4-14 words, no numbering. Return a JSON array of ${PER_CATEGORY} strings.`,
      },
    ],
  });
  return parseList(res.choices[0]?.message?.content ?? "");
}

async function main() {
  const existing = await db.select({ text: schema.prompts.text }).from(schema.prompts);
  const seen = new Set(existing.map((r) => r.text.toLowerCase().trim()));

  const categories = Object.keys(CATEGORY_LABELS) as Category[];
  let inserted = 0;

  for (const category of categories) {
    const candidates = await promptsForCategory(category);
    const fresh = candidates.filter((t) => {
      const key = t.toLowerCase().trim();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    if (fresh.length) {
      await db
        .insert(schema.prompts)
        .values(fresh.map((text) => ({ text, category, source: "generated" })));
    }
    inserted += fresh.length;
    console.log(`${category}: +${fresh.length} (of ${candidates.length} suggested)`);
  }

  console.log(`Inserted ${inserted} new prompts.`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
