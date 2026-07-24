import { drizzle, type NeonHttpDatabase } from "drizzle-orm/neon-http";
import { neon } from "@neondatabase/serverless";
import * as schema from "./schema";

type DB = NeonHttpDatabase<typeof schema>;

// Neon's serverless HTTP driver: every query is a stateless HTTPS request, so
// there is NO connection pool to exhaust. This is the correct driver for
// Vercel serverless — the previous TCP-pool driver (postgres.js) ran out of
// Postgres connections under concurrent load and 500'd /api/pair.
const globalForDb = globalThis as unknown as { drizzle?: DB };

function init(): DB {
  if (globalForDb.drizzle) return globalForDb.drizzle;
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error("DATABASE_URL is not set");
  }
  const sql = neon(connectionString);
  const d = drizzle(sql, { schema });
  globalForDb.drizzle = d;
  return d;
}

/**
 * Lazy proxy: defers the client until the first query so `next build` (which
 * imports modules without DATABASE_URL) doesn't throw, and scripts can load
 * dotenv first.
 */
export const db = new Proxy({} as DB, {
  get(_target, prop) {
    const real = init();
    const value = (real as unknown as Record<string | symbol, unknown>)[prop];
    return typeof value === "function" ? value.bind(real) : value;
  },
});

export { schema };
