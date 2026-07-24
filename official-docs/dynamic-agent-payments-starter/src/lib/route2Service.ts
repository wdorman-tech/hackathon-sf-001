/**
 * Route 2: the agent logs in as its own Dynamic end user and gets its own wallet.
 * No developer API token and no human in the loop — the agent signing token IS its identity.
 * Distinct signing tokens are distinct Dynamic users with entirely separate wallets.
 * https://www.dynamic.xyz/docs/node/agents/overview
 */
import { DynamicEvmWalletClient } from "@dynamic-labs-wallet/node-evm";
import {
  createAuthClient,
  generateSessionKeyPair,
  signSessionMessage,
  type WalletMetadata,
} from "@dynamic-labs-wallet/node";
import { ThresholdSignatureScheme } from "@dynamic-labs-wallet/core";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { publicActions } from "viem";
import {
  AGENT_WALLET_AGENT_ID,
  CHAIN_ID,
  RESOURCE_URL,
  RPC_URL,
  WALLET_PASSWORD,
  requireEnv,
} from "./config.js";
import * as agentTokens from "./agentTokens.js";
import { getUsdcBalance, type UsdcBalance } from "./usdc.js";
import { payForResource, type X402PaymentResult } from "../payWithX402.js";
import { loadWalletMetadata, saveWalletMetadata } from "../store.js";

export async function listAgentIds(): Promise<string[]> {
  const tokenIds = await agentTokens.listAgentIds();
  return [...new Set([AGENT_WALLET_AGENT_ID, ...tokenIds])];
}

// The seed agent's token comes from .env; every agent created via the UI gets
// its own freshly generated token in the (demo-only) token registry instead.
async function resolveSigningToken(agentId: string): Promise<`0x${string}`> {
  const stored = await agentTokens.getToken(agentId);
  if (stored) return stored;
  if (agentId === AGENT_WALLET_AGENT_ID) {
    return requireEnv("AGENT_SIGNING_TOKEN") as `0x${string}`;
  }
  throw new Error(`No signing token on file for agent ${agentId}.`);
}

// Signs in fresh each call — JWTs are short-lived and this is a low-traffic demo,
// so there's no session cache to manage. See node/agents/use-agent-wallets for the
// refresh-token pattern a long-running service should use instead.
async function authenticateAsAgent(agentId: string): Promise<DynamicEvmWalletClient> {
  const environmentId = requireEnv("DYNAMIC_ENVIRONMENT_ID");
  const appOrigin = process.env.APP_ORIGIN ?? "https://example.com";
  const signingToken = await resolveSigningToken(agentId);

  const { publicKeyHex, privateKeyJwk } = await generateSessionKeyPair();
  const agentAccount = privateKeyToAccount(signingToken);
  const auth = createAuthClient({ environmentId, appOrigin });

  const { jwt } = await auth.wallet.signIn({
    address: agentAccount.address,
    signMessage: (message: string) => agentAccount.signMessage({ message }),
    sessionPublicKey: publicKeyHex,
    statement: "Autonomous agent sign-in",
  });

  const client = new DynamicEvmWalletClient({ environmentId });
  await client.authenticateJwt(jwt, {
    getSessionSignature: (message: string) => signSessionMessage(message, privateKeyJwk),
  });
  return client;
}

async function ensureWallet(agentId: string, client: DynamicEvmWalletClient): Promise<WalletMetadata> {
  const existing = await loadWalletMetadata(agentId);
  if (existing) return existing;

  const { walletMetadata } = await client.createWalletAccount({
    thresholdSignatureScheme: ThresholdSignatureScheme.TWO_OF_TWO,
    password: WALLET_PASSWORD,
    backUpToDynamic: true,
  });
  await saveWalletMetadata(agentId, walletMetadata);
  return walletMetadata;
}

export async function getWallet(agentId: string): Promise<WalletMetadata | undefined> {
  return loadWalletMetadata(agentId);
}

export async function getOrCreateWallet(agentId: string): Promise<WalletMetadata> {
  const existing = await loadWalletMetadata(agentId);
  if (existing) return existing;
  return ensureWallet(agentId, await authenticateAsAgent(agentId));
}

// Mints a brand-new agent identity (unless agentId already has a token/wallet):
// generates a signing token, registers it, signs in as that new Dynamic user,
// and creates its wallet — all in one call.
export async function createAgent(agentId: string): Promise<WalletMetadata> {
  const hasToken = (await agentTokens.getToken(agentId)) !== undefined;
  if (!hasToken && agentId !== AGENT_WALLET_AGENT_ID) {
    await agentTokens.saveToken(agentId, generatePrivateKey());
  }
  return getOrCreateWallet(agentId);
}

export async function getBalance(agentId: string): Promise<UsdcBalance> {
  const walletMetadata = await loadWalletMetadata(agentId);
  if (!walletMetadata) throw new Error(`Agent ${agentId} hasn't created a wallet yet.`);
  return getUsdcBalance(walletMetadata.accountAddress as `0x${string}`, CHAIN_ID, RPC_URL);
}

export async function pay(agentId: string): Promise<X402PaymentResult> {
  const client = await authenticateAsAgent(agentId);
  const walletMetadata = await ensureWallet(agentId, client);

  const walletClient = (
    await client.getWalletClient({
      walletMetadata,
      password: WALLET_PASSWORD,
      chainId: CHAIN_ID,
      rpcUrl: RPC_URL,
    })
  ).extend(publicActions);

  return payForResource(walletClient, RESOURCE_URL, agentId);
}
