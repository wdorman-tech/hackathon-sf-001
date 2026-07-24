"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { REASON_TAGS, type Winner } from "@/lib/arena";

interface Pair {
  prompt: string;
  left: { svg: string };
  right: { svg: string };
  token: string;
}

interface Reveal {
  left: string;
  right: string;
}

export default function ArenaPage() {
  const [pair, setPair] = useState<Pair | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [lastWinner, setLastWinner] = useState<Winner | null>(null);
  const [check, setCheck] = useState<{ passed: boolean } | null>(null);
  const [count, setCount] = useState(0);
  // Terac attribution: the panel appends ?submissionId / ?teracSubmissionId /
  // ?taskId to the task URL. Capture on load (persist so it survives reloads)
  // and send with every vote so we can tie votes to a specific participant.
  const terac = useRef<{ submissionId: string | null; taskId: string | null }>({
    submissionId: null,
    taskId: null,
  });

  useEffect(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      const sub = p.get("teracSubmissionId") || p.get("submissionId");
      const task = p.get("taskId");
      if (sub) localStorage.setItem("terac_submission_id", sub);
      if (task) localStorage.setItem("terac_task_id", task);
      terac.current = {
        submissionId: sub || localStorage.getItem("terac_submission_id"),
        taskId: task || localStorage.getItem("terac_task_id"),
      };
    } catch {
      /* ignore (e.g. SSR / storage blocked) */
    }
  }, []);

  const loadPair = useCallback(async () => {
    setReveal(null);
    setLastWinner(null);
    setCheck(null);
    setTags([]);
    setError(null);
    setPair(null);
    const res = await fetch("/api/pair");
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setError(body.error ?? "Failed to load a matchup.");
      return;
    }
    setPair(await res.json());
  }, []);

  useEffect(() => {
    loadPair();
  }, [loadPair]);

  const vote = useCallback(
    async (winner: Winner) => {
      if (!pair || submitting || reveal) return;
      setSubmitting(true);
      const res = await fetch("/api/vote", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          token: pair.token,
          winner,
          reasonTags: tags,
          teracSubmissionId: terac.current.submissionId,
          teracTaskId: terac.current.taskId,
        }),
      });
      setSubmitting(false);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? "Vote failed.");
        return;
      }
      const data = await res.json();
      setLastWinner(winner);
      setReveal(data.reveal ?? null);
      setCount((c) => c + 1);
      if (data.check) setCheck({ passed: !!data.passed });
    },
    [pair, submitting, reveal, tags],
  );

  // Keyboard shortcuts: 1 = left, 2 = right, t = tie, b = both bad, space = next.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (reveal) {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          loadPair();
        }
        return;
      }
      if (e.key === "1") vote("a");
      else if (e.key === "2") vote("b");
      else if (e.key.toLowerCase() === "t") vote("tie");
      else if (e.key.toLowerCase() === "b") vote("both_bad");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [vote, reveal, loadPair]);

  const toggleTag = (t: string) =>
    setTags((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));

  return (
    <div className="flex flex-col items-center">
      <div className="mb-1 text-center text-sm text-neutral-500">
        {count > 0
          ? `${count} vote${count === 1 ? "" : "s"} this session`
          : "Pick the better illustration"}
      </div>

      {error && (
        <div className="my-8 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error}{" "}
          <button onClick={loadPair} className="underline">
            Retry
          </button>
        </div>
      )}

      {!error && !pair && <div className="my-20 text-neutral-400">Loading…</div>}

      {pair && (
        <>
          <h1 className="mb-5 max-w-2xl text-center text-lg font-medium text-neutral-800">
            “{pair.prompt}”
          </h1>

          <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2">
            <Panel
              svg={pair.left.svg}
              side="A"
              revealName={reveal?.left}
              won={reveal ? lastWinner === "a" : undefined}
              onClick={() => vote("a")}
              disabled={!!reveal || submitting}
            />
            <Panel
              svg={pair.right.svg}
              side="B"
              revealName={reveal?.right}
              won={reveal ? lastWinner === "b" : undefined}
              onClick={() => vote("b")}
              disabled={!!reveal || submitting}
            />
          </div>

          {!reveal && (
            <>
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {REASON_TAGS.map((t) => (
                  <button
                    key={t}
                    onClick={() => toggleTag(t)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      tags.includes(t)
                        ? "border-neutral-900 bg-neutral-900 text-white"
                        : "border-neutral-300 bg-white text-neutral-600 hover:border-neutral-400"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
                <button
                  onClick={() => vote("a")}
                  disabled={submitting}
                  className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  ← Left is better <kbd className="ml-1 opacity-60">1</kbd>
                </button>
                <button
                  onClick={() => vote("tie")}
                  disabled={submitting}
                  className="rounded-lg border border-neutral-300 bg-white px-4 py-2.5 text-sm text-neutral-700 hover:border-neutral-400 disabled:opacity-50"
                >
                  Tie <kbd className="ml-1 opacity-60">T</kbd>
                </button>
                <button
                  onClick={() => vote("both_bad")}
                  disabled={submitting}
                  className="rounded-lg border border-neutral-300 bg-white px-4 py-2.5 text-sm text-neutral-700 hover:border-neutral-400 disabled:opacity-50"
                >
                  Both bad <kbd className="ml-1 opacity-60">B</kbd>
                </button>
                <button
                  onClick={() => vote("b")}
                  disabled={submitting}
                  className="rounded-lg bg-neutral-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
                >
                  Right is better <kbd className="ml-1 opacity-60">2</kbd>
                </button>
              </div>
            </>
          )}

          {reveal && (
            <div className="mt-6 flex flex-col items-center gap-3">
              {check && (
                <div
                  className={`rounded-md px-3 py-1 text-sm ${
                    check.passed
                      ? "bg-green-100 text-green-800"
                      : "bg-red-100 text-red-800"
                  }`}
                >
                  {check.passed
                    ? "✓ Attention check passed"
                    : "✗ Attention check — one option was a broken control"}
                </div>
              )}
              <button
                onClick={loadPair}
                className="rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-500"
              >
                Next matchup <kbd className="ml-1 opacity-60">Space</kbd>
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Panel({
  svg,
  side,
  revealName,
  won,
  onClick,
  disabled,
}: {
  svg: string;
  side: string;
  revealName?: string;
  won?: boolean;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col">
      <button
        onClick={onClick}
        disabled={disabled}
        className={`svg-frame relative aspect-square w-full overflow-hidden rounded-xl border bg-white transition ${
          revealName
            ? won
              ? "border-green-500 ring-2 ring-green-400"
              : "border-neutral-200"
            : "border-neutral-200 hover:border-neutral-900 hover:shadow-md"
        } ${disabled ? "cursor-default" : "cursor-pointer"}`}
        // SVG is sanitized server-side (DOMPurify, SVG profile) before storage.
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div className="mt-2 h-5 text-center text-sm">
        {revealName ? (
          <span className={won ? "font-semibold text-green-700" : "text-neutral-500"}>
            {revealName}
          </span>
        ) : (
          <span className="text-neutral-400">Option {side}</span>
        )}
      </div>
    </div>
  );
}
