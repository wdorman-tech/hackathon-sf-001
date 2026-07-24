/**
 * CLI entry point for Route 1 (developer-managed server wallets).
 * See src/lib/route1Service.ts for the actual logic — this is also used by the web UI.
 */
import "dotenv/config";
import { SERVER_WALLET_AGENT_IDS } from "./lib/config.js";
import * as route1 from "./lib/route1Service.js";

async function main(): Promise<void> {
  for (const agentId of SERVER_WALLET_AGENT_IDS) {
    const existing = await route1.getWallet(agentId);
    if (existing) {
      console.log(`[${agentId}] already assigned wallet ${existing.accountAddress}`);
    } else {
      console.log(`[${agentId}] no wallet on file — creating one and assigning it`);
    }

    const result = await route1.pay(agentId);
    console.log(`[${agentId}] got ${result.status} ${result.statusText}`);
    console.log(`[${agentId}] response body:`, result.body.slice(0, 500));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
