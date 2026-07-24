import {
  pgTable,
  serial,
  text,
  integer,
  real,
  boolean,
  timestamp,
  jsonb,
  uniqueIndex,
  index,
} from "drizzle-orm/pg-core";

/**
 * Prompts to render. Each belongs to a category in the taxonomy and is tagged
 * by where it came from (hand-curated core set vs. LLM-augmented breadth).
 */
export const prompts = pgTable(
  "prompts",
  {
    id: serial("id").primaryKey(),
    text: text("text").notNull(),
    category: text("category").notNull(),
    source: text("source").notNull().default("curated"), // 'curated' | 'generated'
    // Experiment split: 'dev' = used in evolution rounds, 'test' = held out for
    // final generalization check, 'pool' = unused reserve.
    split: text("split").notNull().default("pool"),
    active: boolean("active").notNull().default(true),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("prompts_category_idx").on(t.category)],
);

/**
 * A competitor is a (model, technique, config) tuple — NOT a bare model.
 * This lets us pit e.g. "Opus zero-shot" against "Opus best-of-3" and treat
 * prompting/scaffolding techniques as first-class contestants.
 */
export const competitors = pgTable("competitors", {
  id: serial("id").primaryKey(),
  key: text("key").notNull().unique(), // stable slug, e.g. 'opus-bestof3'
  name: text("name").notNull(), // display label, e.g. 'Opus 4.8 (best-of-3)'
  provider: text("provider").notNull(), // 'anthropic' | 'openai' | ...
  modelId: text("model_id").notNull(), // 'claude-opus-4-8'
  technique: text("technique").notNull().default("zero_shot"), // 'zero_shot' | 'best_of_n' | 'self_critique'
  config: jsonb("config").notNull().default({}), // technique params, e.g. { n: 3 }
  active: boolean("active").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

/**
 * One SVG output for a (prompt, competitor) pair. svg is the sanitized version
 * that is safe to render in a browser; svgRaw is the model's original output,
 * preserved for the dataset and debugging.
 */
export const generations = pgTable(
  "generations",
  {
    id: serial("id").primaryKey(),
    promptId: integer("prompt_id")
      .notNull()
      .references(() => prompts.id),
    competitorId: integer("competitor_id")
      .notNull()
      .references(() => competitors.id),
    status: text("status").notNull().default("ok"), // 'ok' | 'error'
    svg: text("svg"), // sanitized, browser-safe
    svgRaw: text("svg_raw"), // model's original output
    error: text("error"),
    tokensIn: integer("tokens_in"),
    tokensOut: integer("tokens_out"),
    latencyMs: integer("latency_ms"),
    costUsd: real("cost_usd"),
    meta: jsonb("meta").notNull().default({}), // e.g. best-of-N candidates, critique text
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    uniqueIndex("generations_prompt_competitor_idx").on(t.promptId, t.competitorId),
    index("generations_prompt_idx").on(t.promptId),
  ],
);

/**
 * An immutable human preference judgment — one row per vote. This table IS the
 * preference dataset; rows are never updated or deleted. competitor ids are
 * denormalized so the dataset is self-contained for analysis/export.
 */
export const votes = pgTable(
  "votes",
  {
    id: serial("id").primaryKey(),
    promptId: integer("prompt_id")
      .notNull()
      .references(() => prompts.id),
    generationAId: integer("generation_a_id")
      .notNull()
      .references(() => generations.id),
    generationBId: integer("generation_b_id")
      .notNull()
      .references(() => generations.id),
    competitorAId: integer("competitor_a_id")
      .notNull()
      .references(() => competitors.id),
    competitorBId: integer("competitor_b_id")
      .notNull()
      .references(() => competitors.id),
    winner: text("winner").notNull(), // 'a' | 'b' | 'tie' | 'both_bad'
    reasonTags: text("reason_tags").array().notNull().default([]),
    raterSession: text("rater_session").notNull(),
    // Terac attribution: the panel appends ?submissionId / ?taskId to the task
    // URL, letting us tie each vote to a specific Terac participant/submission.
    teracSubmissionId: text("terac_submission_id"),
    teracTaskId: text("terac_task_id"),
    userAgent: text("user_agent"),
    isAttentionCheck: boolean("is_attention_check").notNull().default(false),
    attentionPassed: boolean("attention_passed"), // null unless this was a check
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index("votes_prompt_idx").on(t.promptId),
    index("votes_session_idx").on(t.raterSession),
  ],
);

/**
 * Per-browser anonymous session. Used for rate limiting and quality control:
 * a rater that fails attention checks gets a lower qualityScore so their votes
 * can be down-weighted during analysis.
 */
export const raterSessions = pgTable("rater_sessions", {
  token: text("token").primaryKey(),
  teracSubmissionId: text("terac_submission_id"), // links this browser session to a Terac participant
  voteCount: integer("vote_count").notNull().default(0),
  attentionPassed: integer("attention_passed").notNull().default(0),
  attentionFailed: integer("attention_failed").notNull().default(0),
  qualityScore: real("quality_score").notNull().default(1),
  flagged: boolean("flagged").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  lastSeenAt: timestamp("last_seen_at", { withTimezone: true }).notNull().defaultNow(),
});

export type Prompt = typeof prompts.$inferSelect;
export type Competitor = typeof competitors.$inferSelect;
export type Generation = typeof generations.$inferSelect;
export type Vote = typeof votes.$inferSelect;
export type RaterSession = typeof raterSessions.$inferSelect;
