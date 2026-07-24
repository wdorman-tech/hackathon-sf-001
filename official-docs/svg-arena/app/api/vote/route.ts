import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import crypto from "crypto";
import { and, eq, gt, sql } from "drizzle-orm";
import { db, schema } from "@/lib/db";
import { verify } from "@/lib/token";
import { REASON_TAGS, WINNERS, type PairToken, type Winner } from "@/lib/arena";

export const dynamic = "force-dynamic";

const RATE_LIMIT_PER_MIN = 60;

export async function POST(req: NextRequest) {
  const jar = await cookies();
  let sid = jar.get("arena_sid")?.value;
  const setCookie = !sid;
  if (!sid) sid = crypto.randomUUID();

  const body = await req.json().catch(() => null);
  if (!body || typeof body.token !== "string" || !WINNERS.includes(body.winner)) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }
  const winner = body.winner as Winner;
  const reasonTags: string[] = Array.isArray(body.reasonTags)
    ? body.reasonTags.filter((t: unknown): t is string =>
        (REASON_TAGS as readonly string[]).includes(t as string),
      )
    : [];
  // Terac attribution (opaque IDs, not PII). Primary source: the client sends
  // the IDs it captured from the task URL. Robust fallback: the same-origin
  // fetch carries the arena page URL — including ?submissionId/?taskId — in the
  // Referer header, so we can recover them server-side even if the client
  // didn't send them (e.g. a stale bundle or an in-flight session).
  const clean = (v: unknown) =>
    typeof v === "string" && v.length > 0 && v.length <= 128 ? v : null;
  const ref = (() => {
    try {
      const u = new URL(req.headers.get("referer") ?? "");
      return {
        sub:
          u.searchParams.get("teracSubmissionId") ||
          u.searchParams.get("submissionId"),
        task: u.searchParams.get("taskId"),
      };
    } catch {
      return { sub: null, task: null };
    }
  })();
  const teracSubmissionId = clean(body.teracSubmissionId) ?? clean(ref.sub);
  const teracTaskId = clean(body.teracTaskId) ?? clean(ref.task);

  const pair = verify<PairToken>(body.token);
  if (!pair) {
    return NextResponse.json({ error: "Invalid or tampered token" }, { status: 400 });
  }

  // Rate limit per session.
  const since = new Date(Date.now() - 60_000);
  const [{ n }] = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(schema.votes)
    .where(and(eq(schema.votes.raterSession, sid), gt(schema.votes.createdAt, since)));
  if (n >= RATE_LIMIT_PER_MIN) {
    return NextResponse.json({ error: "Too many votes, slow down" }, { status: 429 });
  }

  // Attention check — do not store as preference data; only update rater quality.
  if (pair.check) {
    const passed = winner === pair.correct;
    await db
      .insert(schema.raterSessions)
      .values({
        token: sid,
        teracSubmissionId,
        attentionPassed: passed ? 1 : 0,
        attentionFailed: passed ? 0 : 1,
        qualityScore: passed ? 1 : 0,
        flagged: !passed,
      })
      .onConflictDoUpdate({
        target: schema.raterSessions.token,
        set: {
          attentionPassed: sql`${schema.raterSessions.attentionPassed} + ${passed ? 1 : 0}`,
          attentionFailed: sql`${schema.raterSessions.attentionFailed} + ${passed ? 0 : 1}`,
          teracSubmissionId: sql`coalesce(${schema.raterSessions.teracSubmissionId}, ${teracSubmissionId})`,
          lastSeenAt: sql`now()`,
        },
      });
    // Recompute quality score from accumulated checks.
    await db.execute(sql`
      update ${schema.raterSessions}
      set quality_score = case when (attention_passed + attention_failed) = 0 then 1
        else attention_passed::real / (attention_passed + attention_failed) end,
        flagged = (attention_failed > attention_passed)
      where token = ${sid}
    `);
    const realGenId = pair.leftGenId !== -1 ? pair.leftGenId : pair.rightGenId;
    const realName = await competitorName(realGenId);
    const reveal = {
      left: pair.correct === "a" ? realName : "⚠ Broken control",
      right: pair.correct === "b" ? realName : "⚠ Broken control",
    };
    return withCookie(
      NextResponse.json({ ok: true, check: true, passed, reveal }),
      setCookie ? sid : null,
    );
  }

  // Normal vote — validate both generations exist and belong to this prompt.
  const rows = await db
    .select({
      id: schema.generations.id,
      promptId: schema.generations.promptId,
      competitorId: schema.generations.competitorId,
    })
    .from(schema.generations)
    .where(
      sql`${schema.generations.id} in (${pair.leftGenId}, ${pair.rightGenId})`,
    );
  const left = rows.find((r) => r.id === pair.leftGenId);
  const right = rows.find((r) => r.id === pair.rightGenId);
  if (
    !left ||
    !right ||
    left.promptId !== pair.promptId ||
    right.promptId !== pair.promptId
  ) {
    return NextResponse.json({ error: "Pair no longer valid" }, { status: 409 });
  }

  await db.insert(schema.votes).values({
    promptId: pair.promptId,
    generationAId: left.id,
    generationBId: right.id,
    competitorAId: left.competitorId,
    competitorBId: right.competitorId,
    winner,
    reasonTags,
    raterSession: sid,
    teracSubmissionId,
    teracTaskId,
    userAgent: req.headers.get("user-agent") ?? null,
  });

  await db
    .insert(schema.raterSessions)
    .values({ token: sid, voteCount: 1, teracSubmissionId })
    .onConflictDoUpdate({
      target: schema.raterSessions.token,
      set: {
        voteCount: sql`${schema.raterSessions.voteCount} + 1`,
        teracSubmissionId: sql`coalesce(${schema.raterSessions.teracSubmissionId}, ${teracSubmissionId})`,
        lastSeenAt: sql`now()`,
      },
    });

  const [leftName, rightName] = await Promise.all([
    competitorName(left.id),
    competitorName(right.id),
  ]);

  return withCookie(
    NextResponse.json({ ok: true, reveal: { left: leftName, right: rightName } }),
    setCookie ? sid : null,
  );
}

async function competitorName(genId: number): Promise<string> {
  const [row] = await db
    .select({ name: schema.competitors.name })
    .from(schema.generations)
    .innerJoin(
      schema.competitors,
      eq(schema.generations.competitorId, schema.competitors.id),
    )
    .where(eq(schema.generations.id, genId));
  return row?.name ?? "Unknown";
}

function withCookie(res: NextResponse, sidToSet: string | null) {
  if (sidToSet) {
    res.cookies.set("arena_sid", sidToSet, {
      httpOnly: true,
      sameSite: "lax",
      maxAge: 60 * 60 * 24 * 365,
      path: "/",
    });
  }
  return res;
}
