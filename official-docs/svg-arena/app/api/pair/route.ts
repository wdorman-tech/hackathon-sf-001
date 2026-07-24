import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import crypto from "crypto";
import { and, eq } from "drizzle-orm";
import { db, schema } from "@/lib/db";
import { sign } from "@/lib/token";
import { ATTENTION_CHECK_RATE, DUD_SVG, type PairToken } from "@/lib/arena";

export const dynamic = "force-dynamic";

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

export async function GET() {
  const jar = await cookies();
  let sid = jar.get("arena_sid")?.value;
  const setCookie = !sid;
  if (!sid) sid = crypto.randomUUID();

  // All renderable generations (successful SVG) from *active* competitors only,
  // so deactivating a competitor removes it from the arena.
  const gens = await db
    .select({
      id: schema.generations.id,
      promptId: schema.generations.promptId,
      competitorId: schema.generations.competitorId,
    })
    .from(schema.generations)
    .innerJoin(schema.competitors, eq(schema.generations.competitorId, schema.competitors.id))
    .where(and(eq(schema.generations.status, "ok"), eq(schema.competitors.active, true)));

  if (gens.length < 2) {
    return NextResponse.json(
      { error: "Not enough generations yet. Run the generation script." },
      { status: 503 },
    );
  }

  const isCheck = Math.random() < ATTENTION_CHECK_RATE;

  if (isCheck) {
    // Real (good) SVG vs. a deliberately poor dud. Correct answer = the real one.
    const real = pick(gens);
    const realSvg = await loadSvg(real.id);
    const prompt = await loadPrompt(real.promptId);
    const realOnLeft = Math.random() < 0.5;

    const token: PairToken = {
      promptId: real.promptId,
      leftGenId: realOnLeft ? real.id : -1,
      rightGenId: realOnLeft ? -1 : real.id,
      check: true,
      correct: realOnLeft ? "a" : "b",
      ts: Date.now(),
    };

    return respond(
      {
        prompt: prompt?.text ?? "",
        left: { svg: realOnLeft ? realSvg : DUD_SVG },
        right: { svg: realOnLeft ? DUD_SVG : realSvg },
        token: sign(token),
      },
      setCookie ? sid : null,
    );
  }

  // Normal pair: a prompt with ≥2 generations from distinct competitors.
  const byPrompt = new Map<number, typeof gens>();
  for (const g of gens) {
    const list = byPrompt.get(g.promptId) ?? [];
    list.push(g);
    byPrompt.set(g.promptId, list);
  }
  const eligible = [...byPrompt.entries()].filter(([, list]) => {
    const competitors = new Set(list.map((g) => g.competitorId));
    return competitors.size >= 2;
  });
  if (!eligible.length) {
    return NextResponse.json(
      { error: "No prompt has two competing generations yet." },
      { status: 503 },
    );
  }

  const [promptId, list] = pick(eligible);
  // Two generations from different competitors.
  const first = pick(list);
  const second = pick(list.filter((g) => g.competitorId !== first.competitorId));
  const leftFirst = Math.random() < 0.5;
  const a = leftFirst ? first : second;
  const b = leftFirst ? second : first;

  const [aSvg, bSvg, prompt] = await Promise.all([
    loadSvg(a.id),
    loadSvg(b.id),
    loadPrompt(promptId),
  ]);

  const token: PairToken = {
    promptId,
    leftGenId: a.id,
    rightGenId: b.id,
    check: false,
    ts: Date.now(),
  };

  return respond(
    {
      prompt: prompt?.text ?? "",
      left: { svg: aSvg },
      right: { svg: bSvg },
      token: sign(token),
    },
    setCookie ? sid : null,
  );
}

async function loadSvg(id: number): Promise<string> {
  const [row] = await db
    .select({ svg: schema.generations.svg })
    .from(schema.generations)
    .where(eq(schema.generations.id, id));
  return row?.svg ?? "";
}

async function loadPrompt(id: number) {
  const [row] = await db
    .select({ text: schema.prompts.text })
    .from(schema.prompts)
    .where(eq(schema.prompts.id, id));
  return row;
}

function respond(body: unknown, sidToSet: string | null) {
  const res = NextResponse.json(body);
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
