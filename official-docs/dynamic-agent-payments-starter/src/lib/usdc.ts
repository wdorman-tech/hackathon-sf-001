import { createPublicClient, erc20Abi, formatUnits, http } from "viem";

// USDC contract addresses, per Dynamic's own docs (fireblocks-flow-api.mdx for
// mainnet, moneygram-ramp.mdx for Base Sepolia testnet).
const KNOWN_USDC_ADDRESSES: Record<number, `0x${string}`> = {
  8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", // Base mainnet
  84532: "0x036CbD53842c5426634e7929541eC2318f3dCF7e", // Base Sepolia
};

export function resolveUsdcAddress(chainId: number): `0x${string}` {
  const override = process.env.USDC_ADDRESS;
  if (override) return override as `0x${string}`;

  const known = KNOWN_USDC_ADDRESSES[chainId];
  if (!known) {
    throw new Error(`No known USDC address for chain ${chainId}. Set USDC_ADDRESS in .env.`);
  }
  return known;
}

export interface UsdcBalance {
  raw: string;
  formatted: string;
}

export async function getUsdcBalance(
  accountAddress: `0x${string}`,
  chainId: number,
  rpcUrl: string,
): Promise<UsdcBalance> {
  const usdcAddress = resolveUsdcAddress(chainId);
  const publicClient = createPublicClient({ transport: http(rpcUrl) });

  const [raw, decimals] = await Promise.all([
    publicClient.readContract({
      address: usdcAddress,
      abi: erc20Abi,
      functionName: "balanceOf",
      args: [accountAddress],
    }),
    publicClient.readContract({
      address: usdcAddress,
      abi: erc20Abi,
      functionName: "decimals",
    }),
  ]);

  return { raw: raw.toString(), formatted: formatUnits(raw, decimals) };
}
