import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { WalletMetadata } from "@dynamic-labs-wallet/node";

/**
 * This is a flat-file demo store. It only ever holds `walletMetadata`, which
 * Dynamic's docs classify as non-sensitive — the sensitive `externalServerKeyShares`
 * are never written here. In production, persist this in Redis/Postgres instead;
 * see https://www.dynamic.xyz/docs/node/wallets/server-wallets/storage-best-practices
 */
export type StoredWalletMetadata = WalletMetadata;

const STORE_PATH = process.env.WALLET_STORE_PATH ?? "./data/agent-wallets.json";

type Store = Record<string, StoredWalletMetadata>;

async function readStore(): Promise<Store> {
  try {
    return JSON.parse(await readFile(STORE_PATH, "utf8")) as Store;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw error;
  }
}

async function writeStore(store: Store): Promise<void> {
  await mkdir(dirname(STORE_PATH), { recursive: true });
  await writeFile(STORE_PATH, JSON.stringify(store, null, 2));
}

export async function loadWalletMetadata(
  agentId: string,
): Promise<StoredWalletMetadata | undefined> {
  const store = await readStore();
  return store[agentId];
}

export async function saveWalletMetadata(
  agentId: string,
  walletMetadata: StoredWalletMetadata,
): Promise<void> {
  const store = await readStore();
  store[agentId] = walletMetadata;
  await writeStore(store);
}
