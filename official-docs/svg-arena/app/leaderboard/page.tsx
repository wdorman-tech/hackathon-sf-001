import { eq } from "drizzle-orm";
import { db, schema } from "@/lib/db";
import { computeBradleyTerry, type VoteRow } from "@/lib/ranking";
import { CATEGORY_LABELS } from "@/data/prompts";

export const dynamic = "force-dynamic";

export default async function LeaderboardPage() {
  const competitors = await db
    .select({ id: schema.competitors.id, name: schema.competitors.name })
    .from(schema.competitors)
    .where(eq(schema.competitors.active, true));
  const nameById = new Map(competitors.map((c) => [c.id, c.name]));
  const ids = competitors.map((c) => c.id);

  // Votes joined with prompt category for per-category slicing.
  const votes = await db
    .select({
      competitorAId: schema.votes.competitorAId,
      competitorBId: schema.votes.competitorBId,
      winner: schema.votes.winner,
      category: schema.prompts.category,
    })
    .from(schema.votes)
    .innerJoin(schema.prompts, eq(schema.votes.promptId, schema.prompts.id));

  const overall = computeBradleyTerry(votes as VoteRow[], ids);

  // Per-category winners.
  const categories = [...new Set(votes.map((v) => v.category))].sort();
  const categoryWinners = categories.map((cat) => {
    const standings = computeBradleyTerry(
      votes.filter((v) => v.category === cat) as VoteRow[],
      ids,
    );
    const top = standings.find((s) => s.games > 0);
    return {
      category: cat,
      label: CATEGORY_LABELS[cat as keyof typeof CATEGORY_LABELS] ?? cat,
      winner: top ? nameById.get(top.competitorId) : null,
      rating: top?.rating,
      games: standings.reduce((a, s) => a + s.games, 0) / 2,
    };
  });

  const totalVotes = votes.length;

  return (
    <div>
      <h1 className="mb-1 text-2xl font-semibold">Leaderboard</h1>
      <p className="mb-6 text-sm text-neutral-500">
        Bradley-Terry ratings from {totalVotes.toLocaleString()} pairwise human votes. Ties
        split the point; “both bad” carries no signal.
      </p>

      {overall.every((s) => s.games === 0) ? (
        <div className="rounded-lg border border-neutral-200 bg-white p-6 text-neutral-500">
          No votes yet. Head to the{" "}
          <a href="/" className="text-blue-600 underline">
            Arena
          </a>{" "}
          to cast the first one.
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-left text-neutral-500">
                <tr>
                  <th className="px-4 py-2 font-medium">#</th>
                  <th className="px-4 py-2 font-medium">Competitor</th>
                  <th className="px-4 py-2 text-right font-medium">Rating</th>
                  <th className="px-4 py-2 text-right font-medium">W</th>
                  <th className="px-4 py-2 text-right font-medium">L</th>
                  <th className="px-4 py-2 text-right font-medium">T</th>
                  <th className="px-4 py-2 text-right font-medium">Games</th>
                </tr>
              </thead>
              <tbody>
                {overall.map((s, i) => (
                  <tr key={s.competitorId} className="border-t border-neutral-100">
                    <td className="px-4 py-2 text-neutral-400">{i + 1}</td>
                    <td className="px-4 py-2 font-medium">{nameById.get(s.competitorId)}</td>
                    <td className="px-4 py-2 text-right font-mono">{s.rating}</td>
                    <td className="px-4 py-2 text-right text-green-700">{s.wins}</td>
                    <td className="px-4 py-2 text-right text-red-700">{s.losses}</td>
                    <td className="px-4 py-2 text-right text-neutral-500">{s.ties}</td>
                    <td className="px-4 py-2 text-right text-neutral-500">{s.games}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="mb-3 mt-8 text-lg font-semibold">By category</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {categoryWinners.map((c) => (
              <div key={c.category} className="rounded-xl border border-neutral-200 bg-white p-4">
                <div className="text-xs uppercase tracking-wide text-neutral-400">
                  {c.label}
                </div>
                {c.winner ? (
                  <>
                    <div className="mt-1 font-medium">{c.winner}</div>
                    <div className="text-xs text-neutral-500">
                      Rating {c.rating} · {Math.round(c.games)} games
                    </div>
                  </>
                ) : (
                  <div className="mt-1 text-sm text-neutral-400">No votes yet</div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
