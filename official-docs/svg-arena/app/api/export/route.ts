import { eq } from "drizzle-orm";
import { db, schema } from "@/lib/db";

export const dynamic = "force-dynamic";

/**
 * Export the raw preference dataset as JSONL — one human judgment per line.
 * Each row is self-contained (prompt text/category, both competitors, winner,
 * reason tags, and the rater's quality score) so it can be consumed directly
 * for analysis or model fine-tuning.
 */
export async function GET() {
  const competitors = await db.select().from(schema.competitors);
  const comp = new Map(competitors.map((c) => [c.id, c]));

  const raters = await db
    .select({
      token: schema.raterSessions.token,
      quality: schema.raterSessions.qualityScore,
      flagged: schema.raterSessions.flagged,
    })
    .from(schema.raterSessions);
  const raterMap = new Map(raters.map((r) => [r.token, r]));

  const votes = await db
    .select({
      id: schema.votes.id,
      winner: schema.votes.winner,
      reasonTags: schema.votes.reasonTags,
      raterSession: schema.votes.raterSession,
      teracSubmissionId: schema.votes.teracSubmissionId,
      teracTaskId: schema.votes.teracTaskId,
      createdAt: schema.votes.createdAt,
      competitorAId: schema.votes.competitorAId,
      competitorBId: schema.votes.competitorBId,
      generationAId: schema.votes.generationAId,
      generationBId: schema.votes.generationBId,
      promptText: schema.prompts.text,
      promptCategory: schema.prompts.category,
    })
    .from(schema.votes)
    .innerJoin(schema.prompts, eq(schema.votes.promptId, schema.prompts.id));

  const lines = votes.map((v) => {
    const a = comp.get(v.competitorAId);
    const b = comp.get(v.competitorBId);
    const rater = raterMap.get(v.raterSession);
    return JSON.stringify({
      vote_id: v.id,
      prompt: v.promptText,
      category: v.promptCategory,
      option_a: { competitor: a?.key, model: a?.modelId, technique: a?.technique, generation_id: v.generationAId },
      option_b: { competitor: b?.key, model: b?.modelId, technique: b?.technique, generation_id: v.generationBId },
      winner: v.winner, // 'a' | 'b' | 'tie' | 'both_bad'
      reason_tags: v.reasonTags,
      rater_id: v.raterSession,
      terac_submission_id: v.teracSubmissionId,
      terac_task_id: v.teracTaskId,
      rater_quality: rater?.quality ?? 1,
      rater_flagged: rater?.flagged ?? false,
      created_at: v.createdAt,
    });
  });

  return new Response(lines.join("\n") + (lines.length ? "\n" : ""), {
    headers: {
      "content-type": "application/x-ndjson; charset=utf-8",
      "content-disposition": 'attachment; filename="svg-arena-preferences.jsonl"',
    },
  });
}
