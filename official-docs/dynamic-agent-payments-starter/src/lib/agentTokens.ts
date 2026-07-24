import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

/**
 * DEMO ONLY: persists agent signing tokens — raw secp256k1 private keys that ARE
 * each agent's Dynamic user identity — in a local JSON file so the web UI can spin
 * up new Route 2 agents on demand. In production this belongs in a KMS/HSM/secrets
 * vault, never a plain file; see
 * https://www.dynamic.xyz/docs/node/agents/storage-and-security
 */
const TOKENS_PATH = process.env.AGENT_TOKENS_PATH ?? "./data/route2-agent-tokens.json";

type TokenStore = Record<string, `0x${string}`>;

async function readStore(): Promise<TokenStore> {
  try {
    return JSON.parse(await readFile(TOKENS_PATH, "utf8")) as TokenStore;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

async function writeStore(store: TokenStore): Promise<void> {
  await mkdir(dirname(TOKENS_PATH), { recursive: true });
  await writeFile(TOKENS_PATH, JSON.stringify(store, null, 2));
}

export async function listAgentIds(): Promise<string[]> {
  return Object.keys(await readStore());
}

export async function getToken(agentId: string): Promise<`0x${string}` | undefined> {
  return (await readStore())[agentId];
}

export async function saveToken(agentId: string, token: `0x${string}`): Promise<void> {
  const store = await readStore();
  store[agentId] = token;
  await writeStore(store);
}
