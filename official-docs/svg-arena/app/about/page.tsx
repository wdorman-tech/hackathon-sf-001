export const metadata = { title: "About · SVG Arena" };

export default function AboutPage() {
  return (
    <div className="prose prose-neutral max-w-2xl">
      <h1 className="text-2xl font-semibold">About SVG Arena</h1>

      <p className="mt-4 text-neutral-700">
        SVG Arena benchmarks how well AI models illustrate — not with words, but
        with vector graphics. Models are given the same prompt and asked to
        produce a complete, self-contained SVG illustration. You compare two
        results side by side, blind, and pick the better one.
      </p>

      <h2 className="mt-6 text-lg font-semibold">How it works</h2>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-neutral-700">
        <li>
          Each prompt is sent to several <strong>competitors</strong> — a
          competitor is a model paired with a generation technique (zero-shot,
          best-of-N, or self-critique).
        </li>
        <li>
          Outputs are sanitized and stored. On the Arena, two are shown blind;
          you vote which is better (or tie / both bad), optionally tagging why.
        </li>
        <li>
          Every vote is stored as an immutable row. Together they form an open{" "}
          <strong>human-preference dataset</strong>; the leaderboard&apos;s Elo
          ratings are a byproduct.
        </li>
      </ol>

      <h2 className="mt-6 text-lg font-semibold">Quality &amp; trust</h2>
      <p className="mt-2 text-neutral-700">
        Voting is anonymous. To keep the data honest, a small fraction of
        matchups are <strong>attention checks</strong> (a real illustration vs. a
        deliberately broken control); raters who fail them are flagged and
        down-weighted. Votes are rate-limited per session. All model-generated
        SVG is sanitized server-side before it&apos;s ever rendered.
      </p>

      <h2 className="mt-6 text-lg font-semibold">The dataset</h2>
      <p className="mt-2 text-neutral-700">
        The full preference dataset is downloadable as JSONL — one judgment per
        line, each with the prompt, both competitors, the winner, reason tags,
        and the rater&apos;s quality score.
      </p>
      <p className="mt-3">
        <a
          href="/api/export"
          className="inline-block rounded-lg bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
        >
          Download preferences (.jsonl)
        </a>
      </p>
    </div>
  );
}
