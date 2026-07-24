/**
 * CLI entry point for Route 2 (the agent logs in as its own Dynamic user).
 * See src/lib/route2Service.ts for the actual logic — this is also used by the web UI.
 */
import "dotenv/config";
import { AGENT_WALLET_AGENT_ID } from "./lib/config.js";
import * as route2 from "./lib/route2Service.js";

async function main(): Promise<void> {
  const existing = await route2.getWallet(AGENT_WALLET_AGENT_ID);
  if (existing) {
    console.log(`[${AGENT_WALLET_AGENT_ID}] signing back in to its existing wallet: ${existing.accountAddress}`);
  } else {
    console.log(`[${AGENT_WALLET_AGENT_ID}] no wallet on file — signing in and creating one`);
  }

  const result = await route2.pay(AGENT_WALLET_AGENT_ID);
  console.log(`[${AGENT_WALLET_AGENT_ID}] got ${result.status} ${result.statusText}`);
  console.log(`[${AGENT_WALLET_AGENT_ID}] response body:`, result.body.slice(0, 500));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
