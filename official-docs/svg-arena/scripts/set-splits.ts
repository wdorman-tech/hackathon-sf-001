import { config } from "dotenv";
config({ path: ".env.local" });
config({ path: ".env" });

import { and, eq, inArray } from "drizzle-orm";
import { db, schema } from "../lib/db";

/**
 * Assigns the experiment split:
 *  - dev  : the hand-curated core (evolution rounds vote on these)
 *  - test : a held-out, stratified sample of generated prompts (~3 per category)
 *           used ONLY for the final generalization check — never voted on during
 *           evolution, so a winning prompt can't be overfit to the dev set.
 *  - pool : everything else (reserve).
 */
const TEST_PER_CATEGORY = Number(process.env.TEST_PER_CATEGORY ?? 3);

async function main() {
  // Reset everything to pool.
  await db.update(schema.prompts).set({ split: "pool" });

  // Curated core -> dev.
  await db
    .update(schema.prompts)
    .set({ split: "dev" })
    .where(eq(schema.prompts.source, "curated"));

  // Stratified held-out test set from the generated pool.
  const generated = await db
    .select({ id: schema.prompts.id, category: schema.prompts.category })
    .from(schema.prompts)
    .where(eq(schema.prompts.source, "generated"));

  const byCat = new Map<string, number[]>();
  for (const p of generated.sort((a, b) => a.id - b.id)) {
    const list = byCat.get(p.category) ?? [];
    list.push(p.id);
    byCat.set(p.category, list);
  }
  const testIds: number[] = [];
  for (const ids of byCat.values()) testIds.push(...ids.slice(0, TEST_PER_CATEGORY));
  if (testIds.length) {
    await db
      .update(schema.prompts)
      .set({ split: "test" })
      .where(inArray(schema.prompts.id, testIds));
  }

  const counts = await db
    .select({ split: schema.prompts.split, n: schema.prompts.id })
    .from(schema.prompts);
  const tally: Record<string, number> = {};
  for (const r of counts) tally[r.split] = (tally[r.split] ?? 0) + 1;
  console.log("split counts:", JSON.stringify(tally));
  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
