CREATE TABLE "competitors" (
	"id" serial PRIMARY KEY NOT NULL,
	"key" text NOT NULL,
	"name" text NOT NULL,
	"provider" text NOT NULL,
	"model_id" text NOT NULL,
	"technique" text DEFAULT 'zero_shot' NOT NULL,
	"config" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"active" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "competitors_key_unique" UNIQUE("key")
);
--> statement-breakpoint
CREATE TABLE "generations" (
	"id" serial PRIMARY KEY NOT NULL,
	"prompt_id" integer NOT NULL,
	"competitor_id" integer NOT NULL,
	"status" text DEFAULT 'ok' NOT NULL,
	"svg" text,
	"svg_raw" text,
	"error" text,
	"tokens_in" integer,
	"tokens_out" integer,
	"latency_ms" integer,
	"cost_usd" real,
	"meta" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "prompts" (
	"id" serial PRIMARY KEY NOT NULL,
	"text" text NOT NULL,
	"category" text NOT NULL,
	"source" text DEFAULT 'curated' NOT NULL,
	"active" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "rater_sessions" (
	"token" text PRIMARY KEY NOT NULL,
	"vote_count" integer DEFAULT 0 NOT NULL,
	"attention_passed" integer DEFAULT 0 NOT NULL,
	"attention_failed" integer DEFAULT 0 NOT NULL,
	"quality_score" real DEFAULT 1 NOT NULL,
	"flagged" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"last_seen_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "votes" (
	"id" serial PRIMARY KEY NOT NULL,
	"prompt_id" integer NOT NULL,
	"generation_a_id" integer NOT NULL,
	"generation_b_id" integer NOT NULL,
	"competitor_a_id" integer NOT NULL,
	"competitor_b_id" integer NOT NULL,
	"winner" text NOT NULL,
	"reason_tags" text[] DEFAULT '{}' NOT NULL,
	"rater_session" text NOT NULL,
	"user_agent" text,
	"is_attention_check" boolean DEFAULT false NOT NULL,
	"attention_passed" boolean,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "generations" ADD CONSTRAINT "generations_prompt_id_prompts_id_fk" FOREIGN KEY ("prompt_id") REFERENCES "public"."prompts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "generations" ADD CONSTRAINT "generations_competitor_id_competitors_id_fk" FOREIGN KEY ("competitor_id") REFERENCES "public"."competitors"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "votes" ADD CONSTRAINT "votes_prompt_id_prompts_id_fk" FOREIGN KEY ("prompt_id") REFERENCES "public"."prompts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "votes" ADD CONSTRAINT "votes_generation_a_id_generations_id_fk" FOREIGN KEY ("generation_a_id") REFERENCES "public"."generations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "votes" ADD CONSTRAINT "votes_generation_b_id_generations_id_fk" FOREIGN KEY ("generation_b_id") REFERENCES "public"."generations"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "votes" ADD CONSTRAINT "votes_competitor_a_id_competitors_id_fk" FOREIGN KEY ("competitor_a_id") REFERENCES "public"."competitors"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "votes" ADD CONSTRAINT "votes_competitor_b_id_competitors_id_fk" FOREIGN KEY ("competitor_b_id") REFERENCES "public"."competitors"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "generations_prompt_competitor_idx" ON "generations" USING btree ("prompt_id","competitor_id");--> statement-breakpoint
CREATE INDEX "generations_prompt_idx" ON "generations" USING btree ("prompt_id");--> statement-breakpoint
CREATE INDEX "prompts_category_idx" ON "prompts" USING btree ("category");--> statement-breakpoint
CREATE INDEX "votes_prompt_idx" ON "votes" USING btree ("prompt_id");--> statement-breakpoint
CREATE INDEX "votes_session_idx" ON "votes" USING btree ("rater_session");