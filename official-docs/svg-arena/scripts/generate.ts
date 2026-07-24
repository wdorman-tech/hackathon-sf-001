import { config } from "dotenv";
config({ path: ".env.local" });
config({ path: ".env" });

import pLimit from "p-limit";
import { and, eq } from "drizzle-orm";
import { db, schema } from "../lib/db";
import { generate } from "../lib/generate";

const CONCURRENCY = Number(process.env.GEN_CONCURRENCY ?? 3);

async function main() {
  // Optional filters for cheap validation runs:
  //   COMPETITOR_KEYS=a,b   restrict to these competitor keys
  //   PROMPT_LIMIT=5        only the first N prompts
  const onlyKeys = (process.env.COMPETITOR_KEYS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const promptLimit = process.env.PROMPT_LIMIT
    ? Number(process.env.PROMPT_LIMIT)
    : undefined;
  // PROMPT_ID_MIN / PROMPT_ID_MAX let two runs split the prompt set into
  // disjoint ranges so they can run in parallel without duplicating work.
  const idMin = process.env.PROMPT_ID_MIN ? Number(process.env.PROMPT_ID_MIN) : undefined;
  const idMax = process.env.PROMPT_ID_MAX ? Number(process.env.PROMPT_ID_MAX) : undefined;
  // PROMPT_SPLIT=dev restricts generation to the evolution set (holds out test).
  const split = process.env.PROMPT_SPLIT;

  let prompts = await db
    .select()
    .from(schema.prompts)
    .where(eq(schema.prompts.active, true));
  if (split) prompts = prompts.filter((p) => p.split === split);
  if (idMin !== undefined) prompts = prompts.filter((p) => p.id >= idMin);
  if (idMax !== undefined) prompts = prompts.filter((p) => p.id <= idMax);
  if (promptLimit) prompts = prompts.slice(0, promptLimit);

  let competitors = await db
    .select()
    .from(schema.competitors)
    .where(eq(schema.competitors.active, true));
  if (onlyKeys.length) competitors = competitors.filter((c) => onlyKeys.includes(c.key));

  // Build the work list, skipping (prompt, competitor) pairs already generated.
  const existing = await db
    .select({
      promptId: schema.generations.promptId,
      competitorId: schema.generations.competitorId,
    })
    .from(schema.generations);
  const done = new Set(existing.map((g) => `${g.promptId}:${g.competitorId}`));

  const jobs: { promptId: number; promptText: string; competitor: typeof competitors[number] }[] = [];
  for (const p of prompts) {
    for (const c of competitors) {
      if (!done.has(`${p.id}:${c.id}`)) {
        jobs.push({ promptId: p.id, promptText: p.text, competitor: c });
      }
    }
  }

  console.log(
    `${prompts.length} prompts x ${competitors.length} competitors = ${prompts.length * competitors.length} pairs; ${jobs.length} to generate (concurrency ${CONCURRENCY}).`,
  );

  const limit = pLimit(CONCURRENCY);
  let completed = 0;
  let errors = 0;

  await Promise.all(
    jobs.map((job) =>
      limit(async () => {
        const result = await generate(
          {
            provider: job.competitor.provider,
            modelId: job.competitor.modelId,
            technique: job.competitor.technique,
            config: (job.competitor.config as Record<string, unknown>) ?? {},
          },
          job.promptText,
        );

        // Persist with a small retry — a transient DB blip (e.g. ETIMEDOUT)
        // on one insert must not abort the whole batch run.
        const persist = () =>
          db
            .insert(schema.generations)
            .values({
              promptId: job.promptId,
              competitorId: job.competitor.id,
              status: result.status,
              svg: result.svg,
              svgRaw: result.svgRaw,
              error: result.error,
              tokensIn: result.tokensIn,
              tokensOut: result.tokensOut,
              latencyMs: result.latencyMs,
              costUsd: result.costUsd,
              meta: result.meta,
            })
            .onConflictDoNothing({
              target: [schema.generations.promptId, schema.generations.competitorId],
            });

        let saved = false;
        for (let attempt = 1; attempt <= 3 && !saved; attempt++) {
          try {
            await persist();
            saved = true;
          } catch (e) {
            if (attempt === 3) {
              errors++;
              console.log(`[--] DB-ERR ${job.competitor.key} :: ${(e as Error).message}`);
            } else {
              await new Promise((r) => setTimeout(r, 500 * attempt));
            }
          }
        }
        if (!saved) return;

        completed++;
        if (result.status === "error") errors++;
        const tag = result.status === "ok" ? "ok " : "ERR";
        console.log(
          `[${completed}/${jobs.length}] ${tag} ${job.competitor.key} :: ${job.promptText.slice(0, 48)}${result.error ? ` (${result.error})` : ""}`,
        );
      }),
    ),
  );

  console.log(`Done. ${completed} generated, ${errors} errors.`);
  process.exit(0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
