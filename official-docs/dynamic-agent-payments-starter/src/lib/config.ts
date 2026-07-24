import { randomUUID } from "node:crypto";

export function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var ${name}. Copy .env.example to .env and fill it in.`);
  }
  return value;
}

export const ENVIRONMENT_ID = requireEnv("DYNAMIC_ENVIRONMENT_ID");
export const WALLET_PASSWORD = requireEnv("WALLET_PASSWORD");
export const CHAIN_ID = Number(process.env.CHAIN_ID ?? 84532); // Base Sepolia testnet
export const RPC_URL = process.env.RPC_URL ?? "https://sepolia.base.org";
export const RESOURCE_URL =
  process.env.X402_RESOURCE_URL ?? "https://x402-api.fly.dev/api/price-feed";

// Agents your backend owns (Route 1 — developer-managed server wallets).
export const SERVER_WALLET_AGENT_IDS = ["agent-alpha", "agent-beta"];

// Local label for the agent that signs in as its own Dynamic user (Route 2).
export const AGENT_WALLET_AGENT_ID = "autonomous-agent";

// Agent IDs are used as JSON object keys and URL path segments — validate
// user-supplied ones against a strict allowlist rather than trusting them
// (guards against oddities like a literal "constructor" or "__proto__" key).
const AGENT_ID_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$/;
const RESERVED_AGENT_IDS = new Set(["__proto__", "constructor", "prototype"]);

export function isValidAgentId(id: unknown): id is string {
  return typeof id === "string" && AGENT_ID_PATTERN.test(id) && !RESERVED_AGENT_IDS.has(id);
}

export function randomAgentId(prefix: string): string {
  return `${prefix}-${randomUUID().slice(0, 8)}`;
}
