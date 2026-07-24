import { config } from "dotenv";
config({ path: ".env.local" });
config({ path: ".env" });

import { notInArray } from "drizzle-orm";
import { db, schema } from "../lib/db";
import { COMPETITORS } from "../data/competitors";
import { PROMPTS } from "../data/prompts";

async function main() {
  // Competitors — upsert on the unique `key`, then sync the active flag so the
  // live roster matches the seed list exactly (any competitor not listed here
  // is deactivated, e.g. when swapping providers).
  for (const c of COMPETITORS) {
    await db
      .insert(schema.competitors)
      .values({
        key: c.key,
        name: c.name,
        provider: c.provider,
        modelId: c.modelId,
        technique: c.technique,
        config: c.config,
        active: true,
      })
      .onConflictDoUpdate({
        target: schema.competitors.key,
        set: {
          name: c.name,
          provider: c.provider,
          modelId: c.modelId,
          technique: c.technique,
          config: c.config,
          active: true,
        },
      });
  }
  const keys = COMPETITORS.map((c) => c.key);
  await db
    .update(schema.competitors)
    .set({ active: false })
    .where(notInArray(schema.competitors.key, keys));
  console.log(`Seeded ${COMPETITORS.length} competitors (others deactivated).`);

  // Prompts — insert only those whose text isn't already present.
  const existing = await db.select({ text: schema.prompts.text }).from(schema.prompts);
  const seen = new Set(existing.map((r) => r.text));
  const toInsert = PROMPTS.filter((p) => !seen.has(p.text));
  if (toInsert.length) {
    await db.insert(schema.prompts).values(
      toInsert.map((p) => ({ text: p.text, category: p.category, source: "curated" })),
    );
  }
  console.log(`Seeded ${toInsert.length} new prompts (${PROMPTS.length} total in set).`);

  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
