ALTER TABLE "rater_sessions" ADD COLUMN "terac_submission_id" text;--> statement-breakpoint
ALTER TABLE "votes" ADD COLUMN "terac_submission_id" text;--> statement-breakpoint
ALTER TABLE "votes" ADD COLUMN "terac_task_id" text;