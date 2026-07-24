import { defineConfig } from "drizzle-kit";
import { config } from "dotenv";

// Load env for CLI usage (drizzle-kit runs outside Next.js).
config({ path: ".env.local" });
config({ path: ".env" });

export default defineConfig({
  schema: "./lib/db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: process.env.DATABASE_URL!,
  },
  verbose: true,
  strict: true,
});
