# Agent server wallets + x402

A Node.js example showing two ways to give an AI agent its own wallet with
[Dynamic](https://www.dynamic.xyz/), and have that agent pay for an
x402-gated API with it — as CLI scripts and as a small web UI.

Both routes use Dynamic's **Node SDK** (`@dynamic-labs-wallet/*`) — this is
backend/server-side code, not the browser/React SDK.

## Contents

- [The two routes](#the-two-routes)
- [Project structure](#project-structure)
- [Setup](#setup)
- [Running it](#running-it)
  - [CLI](#cli)
  - [Web UI](#web-ui)
- [Web UI API reference](#web-ui-api-reference)
- [Testnet vs. mainnet](#testnet-vs-mainnet)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)
- [Reference / docs links](#reference--docs-links)

## The two routes

### Route 1 — developer-managed server wallets

Your backend creates and fully owns the wallet, authenticating with its own
API token; no user or agent identity is involved. "Assigning" a wallet to an
agent is just an `agentId -> walletMetadata` mapping your application keeps
(see `src/store.ts`). This is the simplest option when agents act on your
platform's behalf rather than as accountable identities of their own.

```
DYNAMIC_API_TOKEN (your backend's credential)
        │
        ▼
createWalletAccount()  →  assign to "agent-alpha", "agent-beta", ...
        │
        ▼
each agent calls getWalletClient() + x402-fetch to pay for a resource
```

CLI: `src/serverWallets.ts` · Web UI logic: `src/lib/route1Service.ts`

### Route 2 — the agent logs in as its own Dynamic user

No developer API token, no human in the loop. The agent holds an **agent
signing token** — a private key that *is* its identity, the same way a
person's wallet key is theirs. It signs a Sign-In-With-Ethereum (SIWE)
message with that key to mint its own Dynamic user JWT, then creates or
reuses a wallet the same way any signed-in user would. Different signing
tokens are different Dynamic users with entirely separate wallets — a fleet
of agents never shares a wallet or credential.

```
AGENT_SIGNING_TOKEN (the agent's own identity)
        │
        ▼
SIWE sign-in  →  Dynamic user JWT  →  createWalletAccount() as that user
        │
        ▼
agent calls getWalletClient() + x402-fetch to pay for a resource
```

CLI: `src/agentWallets.ts` · Web UI logic: `src/lib/route2Service.ts`

### Which one to use

Use **Route 1** when your backend should retain custody of every wallet —
simplest to operate, one credential for your whole fleet. Use **Route 2**
when each agent should be its own accountable Dynamic user — useful for
distinct identities, audit trails, or agents that may eventually delegate
to/from human users.

## Project structure

```
src/
  server.ts              Web UI: Express app + REST API over both routes
  serverWallets.ts        CLI entry point for Route 1
  agentWallets.ts          CLI entry point for Route 2
  payWithX402.ts          Shared x402-fetch payment helper
  store.ts                 Flat-file walletMetadata store (agentId -> wallet)
  lib/
    config.ts              Env vars, defaults, agent-id validation/generation
    route1Service.ts       Route 1 logic: create/assign wallets, pay
    route2Service.ts       Route 2 logic: sign-in, create/reuse wallets, pay
    idRegistry.ts           Generic "known agent ids" list, backs Route 1's agents
    agentTokens.ts          Route 2's per-agent signing-token store (demo-only, sensitive)
    usdc.ts                 USDC balance lookups via viem
public/
  index.html               Web UI markup (tabs, per-route Agents/Create sections)
  app.js                    Web UI client logic (fetch calls, DOM rendering)
  style.css                 Web UI styling
data/                       Created at runtime — gitignored, see Security notes
```

## Setup

1. Create a Dynamic project and grab your environment ID:
   https://app.dynamic.xyz/dashboard/developer/api
2. Enable **multiple embedded wallets per chain** in the dashboard
   (Embedded Wallets settings) — required for server wallets.
3. Install dependencies:
   ```bash
   npm install
   ```
4. Copy the env file and fill in real values:
   ```bash
   cp .env.example .env
   ```

| Variable | Used by | Notes |
| --- | --- | --- |
| `DYNAMIC_ENVIRONMENT_ID` | both | From the dashboard link above. |
| `DYNAMIC_API_TOKEN` | Route 1 | Dashboard → Developer → API → create a new API token. |
| `AGENT_SIGNING_TOKEN` | Route 2 (seed agent) | A 32-byte secp256k1 private key. Generate one with `node -e "console.log(require('viem/accounts').generatePrivateKey())"`. Rotating it creates a brand-new Dynamic user. |
| `APP_ORIGIN` | Route 2 | Origin the agent presents as during sign-in; must be allow-listed under Dashboard → Developer → CORS. |
| `WALLET_PASSWORD` | both | Protects MPC key shares backed up to Dynamic (`backUpToDynamic: true`). Use a real, strong value — not a placeholder. |
| `CHAIN_ID` / `RPC_URL` | both | Default to Base Sepolia testnet. See [Testnet vs. mainnet](#testnet-vs-mainnet). |
| `USDC_ADDRESS` | web UI balance check | Auto-resolved for Base (`8453`) and Base Sepolia (`84532`); set explicitly for any other chain. |
| `X402_RESOURCE_URL` | both | Defaults to Dynamic's public demo x402 API. |

5. Fund the resulting wallet address(es) with a little testnet (or mainnet)
   USDC before paying — the demo endpoint is a real x402-gated API and will
   charge per request.

## Running it

### CLI

```bash
npm run route:server-wallets   # Route 1 — agent-alpha, agent-beta
npm run route:agent-wallets    # Route 2 — the seed "autonomous-agent"
```

Each run pays the configured `X402_RESOURCE_URL` once per agent and prints
the result. Re-running reuses whatever wallet(s) were created on the first
run (loaded from `data/agent-wallets.json`).

### Web UI

```bash
npm run ui
```

Opens a dashboard at **http://localhost:3000**, with a tab per route:

- **Agents** — every known agent as a card (address, live USDC balance, and
  buttons to create/refresh its wallet, check its balance, and pay the x402
  resource). Every click is logged with the raw API response in the activity
  log at the bottom of the page.
- **Create agent** — an id field (leave blank for an auto-generated one) plus
  a button that registers a new agent and creates its wallet in one step. On
  Route 2 this also mints a **brand-new agent signing token**, i.e. a
  brand-new Dynamic user — that's the actual point of that route.
- **Docs** links at the top of each tab, straight to the relevant Dynamic doc
  and the x402 recipe.

## Web UI API reference

`src/server.ts` exposes a small REST API; the frontend is just a client of
it, so you can drive the same actions with `curl` or build another UI on top.

| Method & path | Description |
| --- | --- |
| `GET /api/config` | Current chain ID, RPC URL, and x402 resource URL. |
| `GET /api/route1/agents` | List Route 1 agents and their wallets (if created). |
| `POST /api/route1/agents` | Create a new Route 1 agent + wallet. Body: `{ "agentId"?: string }`. |
| `POST /api/route1/agents/:agentId/wallet` | Create/assign the wallet for an existing agent. |
| `GET /api/route1/agents/:agentId/balance` | USDC balance for that agent's wallet. |
| `POST /api/route1/agents/:agentId/pay` | Pay the configured x402 resource. |
| `GET /api/route2/agents` | List Route 2 agents and their wallets. |
| `POST /api/route2/agents` | Mint a new agent signing token, sign in, and create its wallet. Body: `{ "agentId"?: string }`. |
| `POST /api/route2/agents/:agentId/wallet` | Sign in as an existing agent and create/reuse its wallet. |
| `GET /api/route2/agents/:agentId/balance` | USDC balance for that agent's wallet. |
| `POST /api/route2/agents/:agentId/pay` | Sign in and pay the configured x402 resource. |

`agentId` path params are validated against each route's known-agent list
(404 on an unknown id); `agentId` in a create-agent body is validated against
`^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$` (400 otherwise).

## Testnet vs. mainnet

`.env.example` defaults to **Base Sepolia** (`CHAIN_ID=84532`,
`RPC_URL=https://sepolia.base.org`) so you can explore the app without
spending real funds. Switch to `CHAIN_ID=8453` and
`RPC_URL=https://mainnet.base.org` for Base mainnet, where the
[Fireblocks x402 facilitator](https://developers.fireblocks.com/docs/x402-facilitator-overview)
settles zero-fee USDC payments.

The public demo endpoint (`X402_RESOURCE_URL`) is documented as running on
Base — it's unconfirmed whether it accepts Sepolia payments. If a payment on
testnet fails with something other than an insufficient-balance error, that's
likely the endpoint rejecting the network; point `X402_RESOURCE_URL` at your
own testnet-aware x402 resource, or switch to mainnet and fund with real
USDC.

## Security notes

- `data/agent-wallets.json` only ever holds non-sensitive `walletMetadata`
  (wallet IDs and addresses). No key material is written to disk for Route 1
  or the seed Route 2 agent — both use `backUpToDynamic: true`, so Dynamic's
  key-share service holds the sensitive MPC shares, guarded by
  `WALLET_PASSWORD`.
- **Exception:** agents created via the UI's "Create agent" button on Route 2
  each need their own signing token, generated on the fly. The demo persists
  those in `data/route2-agent-tokens.json` in **plaintext** (see
  `src/lib/agentTokens.ts`) so the UI can reuse them across requests. That
  token *is* the agent's Dynamic user identity — in production it belongs in
  a KMS/HSM/secrets vault, never a plain file. This exists purely so the demo
  UI has somewhere to put it; don't carry this pattern into anything real.
- Never commit `.env` or a real `WALLET_PASSWORD` / `AGENT_SIGNING_TOKEN`.
  `.gitignore` already excludes `.env*` (except `.env.example`) and `data/`
  (which covers both files above).
- In a real deployment, replace the flat-file stores with a proper cache
  (`walletMetadata`) and put `WALLET_PASSWORD` / signing tokens in a secrets
  manager (KMS, Vault, AWS/GCP Secrets Manager), not local files or process
  env vars sourced from a plain `.env` file.

## Troubleshooting

- **`"ERC20: transfer amount exceeds balance"`** — the wallet negotiated the
  x402 payment correctly but doesn't hold enough USDC yet. Fund it and retry.
- **`Missing required env var ...`** — copy `.env.example` to `.env` and fill
  in the named variable; see the table in [Setup](#setup).
- **Route 2 sign-in fails** — check that `APP_ORIGIN` is allow-listed under
  Dashboard → Developer → CORS, and that the sign-in method (wallet/SIWE) is
  enabled under Dashboard → Auth methods.
- **`agentId must be 1-39 lowercase letters, digits, or hyphens`** — the
  create-agent validation rejected your input; use a plain slug.

## Reference / docs links

- [Server Wallets](https://www.dynamic.xyz/docs/node/wallets/server-wallets/overview) — Route 1
- [Storage Best Practices](https://www.dynamic.xyz/docs/node/wallets/server-wallets/storage-best-practices) — `walletMetadata` vs. key-share storage
- [Agent Wallets overview](https://www.dynamic.xyz/docs/node/agents/overview) — Route 2
- [Agent Wallets: Storage & Security](https://www.dynamic.xyz/docs/node/agents/storage-and-security) — what to persist and the security model
- [Agent Payments](https://www.dynamic.xyz/docs/overview/agents/agent-payments) — x402 and Tempo MPP for agents
- [Using Dynamic with x402](https://www.dynamic.xyz/docs/recipes/integrations/x402/implementation) — the payment flow both routes use
- [Node SDK Quickstart](https://www.dynamic.xyz/docs/node/quickstart)
