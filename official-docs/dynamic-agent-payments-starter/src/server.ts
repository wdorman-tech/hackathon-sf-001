/**
 * Web UI for the two wallet-assignment routes. This is the same logic as
 * serverWallets.ts / agentWallets.ts (src/lib/route1Service.ts, route2Service.ts),
 * exposed over HTTP so each step — including minting brand-new agents — can be
 * triggered manually from a browser instead of a CLI run.
 */
import "dotenv/config";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import express, { type Request, type Response } from "express";
import { CHAIN_ID, RESOURCE_URL, RPC_URL, isValidAgentId, randomAgentId } from "./lib/config.js";
import * as route1 from "./lib/route1Service.js";
import * as route2 from "./lib/route2Service.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT ?? 3000);

const app = express();
app.use(express.json());
app.use(express.static(join(__dirname, "..", "public")));

function handle(fn: (req: Request, res: Response) => Promise<void>) {
  return (req: Request, res: Response) => {
    fn(req, res).catch((error: unknown) => {
      console.error(error);
      res.status(500).json({ error: error instanceof Error ? error.message : String(error) });
    });
  };
}

// Validates the :agentId path param against a route's known-agent list, rather
// than trusting whatever the client sends.
async function requireKnownAgentId(
  req: Request,
  res: Response,
  listAgentIds: () => Promise<string[]>,
): Promise<string | undefined> {
  const agentId = req.params.agentId;
  const known = await listAgentIds();
  if (typeof agentId === "string" && known.includes(agentId)) return agentId;
  res.status(404).json({ error: `Unknown agent id: ${JSON.stringify(agentId)}` });
  return undefined;
}

// Resolves the agentId for a "create a new agent" POST: an explicit id from the
// request body (validated against the allowlist) or an auto-generated one.
function resolveNewAgentId(req: Request, res: Response, prefix: string): string | undefined {
  const requested = (req.body as { agentId?: unknown } | undefined)?.agentId;
  if (requested === undefined || requested === "") return randomAgentId(prefix);
  if (isValidAgentId(requested)) return requested;
  res.status(400).json({ error: "agentId must be 1-39 lowercase letters, digits, or hyphens." });
  return undefined;
}

app.get(
  "/api/config",
  handle(async (_req, res) => {
    res.json({ chainId: CHAIN_ID, rpcUrl: RPC_URL, resourceUrl: RESOURCE_URL });
  }),
);

// --- Route 1: developer-managed server wallets --------------------------------

app.get(
  "/api/route1/agents",
  handle(async (_req, res) => {
    const agentIds = await route1.listAgentIds();
    const agents = await Promise.all(
      agentIds.map(async (agentId) => ({ agentId, wallet: (await route1.getWallet(agentId)) ?? null })),
    );
    res.json({ agents });
  }),
);

app.post(
  "/api/route1/agents",
  handle(async (req, res) => {
    const agentId = resolveNewAgentId(req, res, "agent");
    if (!agentId) return;
    res.json({ agentId, wallet: await route1.createAgent(agentId) });
  }),
);

app.post(
  "/api/route1/agents/:agentId/wallet",
  handle(async (req, res) => {
    const agentId = await requireKnownAgentId(req, res, route1.listAgentIds);
    if (!agentId) return;
    res.json({ wallet: await route1.getOrAssignWallet(agentId) });
  }),
);

app.get(
  "/api/route1/agents/:agentId/balance",
  handle(async (req, res) => {
    const agentId = await requireKnownAgentId(req, res, route1.listAgentIds);
    if (!agentId) return;
    res.json({ balance: await route1.getBalance(agentId) });
  }),
);

app.post(
  "/api/route1/agents/:agentId/pay",
  handle(async (req, res) => {
    const agentId = await requireKnownAgentId(req, res, route1.listAgentIds);
    if (!agentId) return;
    res.json({ result: await route1.pay(agentId) });
  }),
);

// --- Route 2: agent logs in as its own Dynamic user ----------------------------

app.get(
  "/api/route2/agents",
  handle(async (_req, res) => {
    const agentIds = await route2.listAgentIds();
    const agents = await Promise.all(
      agentIds.map(async (agentId) => ({ agentId, wallet: (await route2.getWallet(agentId)) ?? null })),
    );
    res.json({ agents });
  }),
);

app.post(
  "/api/route2/agents",
  handle(async (req, res) => {
    const agentId = resolveNewAgentId(req, res, "autonomous-agent");
    if (!agentId) return;
    res.json({ agentId, wallet: await route2.createAgent(agentId) });
  }),
);

app.post(
  "/api/route2/agents/:agentId/wallet",
  handle(async (req, res) => {
    const agentId = await requireKnownAgentId(req, res, route2.listAgentIds);
    if (!agentId) return;
    res.json({ wallet: await route2.getOrCreateWallet(agentId) });
  }),
);

app.get(
  "/api/route2/agents/:agentId/balance",
  handle(async (req, res) => {
    const agentId = await requireKnownAgentId(req, res, route2.listAgentIds);
    if (!agentId) return;
    res.json({ balance: await route2.getBalance(agentId) });
  }),
);

app.post(
  "/api/route2/agents/:agentId/pay",
  handle(async (req, res) => {
    const agentId = await requireKnownAgentId(req, res, route2.listAgentIds);
    if (!agentId) return;
    res.json({ result: await route2.pay(agentId) });
  }),
);

app.listen(PORT, () => {
  console.log(`Agent wallet UI running at http://localhost:${PORT}`);
});
