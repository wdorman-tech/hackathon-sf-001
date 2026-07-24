/**
 * Elo ranking over pairwise votes. 'tie' splits the point; 'both_bad' carries
 * no preference signal and is skipped. This is intentionally simple and
 * order-dependent; for a published leaderboard we can later swap in
 * Bradley-Terry (order-independent MLE) over the same vote rows.
 */
export interface VoteRow {
  competitorAId: number;
  competitorBId: number;
  winner: string; // 'a' | 'b' | 'tie' | 'both_bad'
}

export interface Standing {
  competitorId: number;
  rating: number;
  wins: number;
  losses: number;
  ties: number;
  games: number;
}

const K = 32;
const BASE = 1000;

/**
 * Bradley-Terry ratings via the standard MM (minorization-maximization)
 * algorithm. Unlike Elo, this is ORDER-INDEPENDENT — it fits each competitor's
 * strength to the full set of pairwise outcomes at once, so it can't produce
 * Elo's artifact (a top rating with a losing record). Ties count as half a win
 * to each side; 'both_bad' carries no signal and is skipped.
 *
 * Strengths are converted to an Elo-like scale for readability:
 *   rating = 1000 + 400 * log10(strength / geometric-mean strength).
 */
export function computeBradleyTerry(
  votes: VoteRow[],
  competitorIds: number[],
): Standing[] {
  const ids = competitorIds;
  const n = ids.length;
  const idx = new Map(ids.map((id, i) => [id, i]));

  const wins = new Array(n).fill(0); // raw wins (for display)
  const losses = new Array(n).fill(0);
  const ties = new Array(n).fill(0);
  const wWins = new Array(n).fill(0); // weighted wins (ties = 0.5) for the fit
  const games = Array.from({ length: n }, () => new Array(n).fill(0));

  for (const v of votes) {
    if (v.winner === "both_bad") continue;
    const i = idx.get(v.competitorAId);
    const j = idx.get(v.competitorBId);
    if (i === undefined || j === undefined) continue;
    games[i][j]++;
    games[j][i]++;
    if (v.winner === "tie") {
      wWins[i] += 0.5;
      wWins[j] += 0.5;
      ties[i]++;
      ties[j]++;
    } else if (v.winner === "a") {
      wWins[i] += 1;
      wins[i]++;
      losses[j]++;
    } else {
      wWins[j] += 1;
      wins[j]++;
      losses[i]++;
    }
  }

  // MM iterations.
  let p = new Array(n).fill(1);
  for (let iter = 0; iter < 500; iter++) {
    const pNew = new Array(n).fill(0);
    for (let i = 0; i < n; i++) {
      let denom = 0;
      for (let j = 0; j < n; j++) {
        if (i === j || games[i][j] === 0) continue;
        denom += games[i][j] / (p[i] + p[j]);
      }
      pNew[i] = denom > 0 ? wWins[i] / denom : p[i];
    }
    // Normalize to geometric mean = 1 for numerical stability.
    const logMean =
      pNew.reduce((s, x) => s + Math.log(x > 0 ? x : 1e-12), 0) / n;
    const gm = Math.exp(logMean);
    for (let i = 0; i < n; i++) pNew[i] = (pNew[i] || 1e-12) / gm;
    let maxDelta = 0;
    for (let i = 0; i < n; i++) maxDelta = Math.max(maxDelta, Math.abs(pNew[i] - p[i]));
    p = pNew;
    if (maxDelta < 1e-9) break;
  }

  return ids
    .map((id, i) => ({
      competitorId: id,
      rating: Math.round(1000 + 400 * Math.log10(p[i] > 0 ? p[i] : 1e-12)),
      wins: wins[i],
      losses: losses[i],
      ties: ties[i],
      games: wins[i] + losses[i] + ties[i],
    }))
    .sort((a, b) => b.rating - a.rating);
}

function expected(a: number, b: number): number {
  return 1 / (1 + Math.pow(10, (b - a) / 400));
}

export function computeElo(votes: VoteRow[], competitorIds: number[]): Standing[] {
  const rating = new Map<number, number>();
  const wins = new Map<number, number>();
  const losses = new Map<number, number>();
  const ties = new Map<number, number>();
  const games = new Map<number, number>();
  for (const id of competitorIds) {
    rating.set(id, BASE);
    wins.set(id, 0);
    losses.set(id, 0);
    ties.set(id, 0);
    games.set(id, 0);
  }

  const inc = (m: Map<number, number>, id: number, by = 1) =>
    m.set(id, (m.get(id) ?? 0) + by);

  for (const v of votes) {
    if (v.winner === "both_bad") continue;
    const a = v.competitorAId;
    const b = v.competitorBId;
    if (!rating.has(a) || !rating.has(b)) continue;

    const ra = rating.get(a)!;
    const rb = rating.get(b)!;
    const ea = expected(ra, rb);
    const eb = expected(rb, ra);

    // Score for A.
    let sa: number;
    if (v.winner === "a") sa = 1;
    else if (v.winner === "b") sa = 0;
    else sa = 0.5; // tie

    rating.set(a, ra + K * (sa - ea));
    rating.set(b, rb + K * (1 - sa - eb));

    inc(games, a);
    inc(games, b);
    if (v.winner === "tie") {
      inc(ties, a);
      inc(ties, b);
    } else if (v.winner === "a") {
      inc(wins, a);
      inc(losses, b);
    } else {
      inc(wins, b);
      inc(losses, a);
    }
  }

  return competitorIds
    .map((id) => ({
      competitorId: id,
      rating: Math.round(rating.get(id)!),
      wins: wins.get(id)!,
      losses: losses.get(id)!,
      ties: ties.get(id)!,
      games: games.get(id)!,
    }))
    .sort((x, y) => y.rating - x.rating);
}
