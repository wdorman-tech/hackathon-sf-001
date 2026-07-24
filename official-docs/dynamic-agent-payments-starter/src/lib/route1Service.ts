/**
 * Route 1: developer-managed server wallets.
 * Your backend creates and owns these wallets outright — no user is ever involved.
 * https://www.dynamic.xyz/docs/node/wallets/server-wallets/overview
 */
import { DynamicEvmWalletClient } from "@dynamic-labs-wallet/node-evm";
import { ThresholdSignatureScheme, type WalletMetadata } from "@dynamic-labs-wallet/node";
import { publicActions } from "viem";
import {
  CHAIN_ID,
  RESOURCE_URL,
  RPC_URL,
  SERVER_WALLET_AGENT_IDS,
  WALLET_PASSWORD,
  requireEnv,
} from "./config.js";
import { createIdRegistry } from "./idRegistry.js";
import { getUsdcBalance, type UsdcBalance } from "./usdc.js";
import { payForResource, type X402PaymentResult } from "../payWithX402.js";
import { loadWalletMetadata, saveWalletMetadata } from "../store.js";

const agentRegistry = createIdRegistry(
  process.env.ROUTE1_AGENTS_PATH ?? "./data/route1-agents.json",
  SERVER_WALLET_AGENT_IDS,
);

export async function listAgentIds(): Promise<string[]> {
  return agentRegistry.list();
}

let cachedClient: Promise<DynamicEvmWalletClient> | undefined;

function getEvmClient(): Promise<DynamicEvmWalletClient> {
  if (!cachedClient) {
    cachedClient = (async () => {
      const client = new DynamicEvmWalletClient({ environmentId: requireEnv("DYNAMIC_ENVIRONMENT_ID") });
      await client.authenticateApiToken(requireEnv("DYNAMIC_API_TOKEN"));
      return client;
    })();
  }
  return cachedClient;
}

export async function getWallet(agentId: string): Promise<WalletMetadata | undefined> {
  return loadWalletMetadata(agentId);
}

export async function getOrAssignWallet(agentId: string): Promise<WalletMetadata> {
  const existing = await loadWalletMetadata(agentId);
  if (existing) return existing;

  const evmClient = await getEvmClient();
  const { walletMetadata } = await evmClient.createWalletAccount({
    thresholdSignatureScheme: ThresholdSignatureScheme.TWO_OF_TWO,
    password: WALLET_PASSWORD,
    // Dynamic stores the key shares for us, so this demo doesn't need its own vault.
    backUpToDynamic: true,
  });

  await saveWalletMetadata(agentId, walletMetadata);
  return walletMetadata;
}

export async function createAgent(agentId: string): Promise<WalletMetadata> {
  await agentRegistry.register(agentId);
  return getOrAssignWallet(agentId);
}

export async function getBalance(agentId: string): Promise<UsdcBalance> {
  const walletMetadata = await loadWalletMetadata(agentId);
  if (!walletMetadata) throw new Error(`No wallet assigned to ${agentId} yet.`);
  return getUsdcBalance(walletMetadata.accountAddress as `0x${string}`, CHAIN_ID, RPC_URL);
}

export async function pay(agentId: string): Promise<X402PaymentResult> {
  const walletMetadata = await getOrAssignWallet(agentId);
  const evmClient = await getEvmClient();

  const walletClient = (
    await evmClient.getWalletClient({
      walletMetadata,
      password: WALLET_PASSWORD,
      chainId: CHAIN_ID,
      rpcUrl: RPC_URL,
    })
  ).extend(publicActions);

  return payForResource(walletClient, RESOURCE_URL, agentId);
}
