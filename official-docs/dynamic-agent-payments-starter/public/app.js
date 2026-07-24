const logEl = document.getElementById("log");

function logEvent(title, ok, detail) {
  const entry = document.createElement("div");
  entry.className = `log-entry ${ok ? "ok" : "err"}`;

  const header = document.createElement("div");
  const ts = document.createElement("span");
  ts.className = "ts";
  ts.textContent = `[${new Date().toLocaleTimeString()}] `;
  const titleEl = document.createElement("span");
  titleEl.className = "title";
  titleEl.textContent = title;
  header.append(ts, titleEl);

  const pre = document.createElement("pre");
  pre.style.margin = "0.35rem 0 0";
  pre.style.font = "inherit";
  pre.textContent = typeof detail === "string" ? detail : JSON.stringify(detail, null, 2);

  entry.append(header, pre);
  logEl.prepend(entry);
}

async function api(method, path, jsonBody) {
  const res = await fetch(path, {
    method,
    headers: jsonBody === undefined ? undefined : { "Content-Type": "application/json" },
    body: jsonBody === undefined ? undefined : JSON.stringify(jsonBody),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    logEvent(`${method} ${path} -> ${res.status}`, false, body);
    throw new Error(body.error ?? `${res.status} ${res.statusText}`);
  }
  logEvent(`${method} ${path} -> ${res.status}`, true, body);
  return body;
}

function formatWallet(wallet) {
  return wallet ? wallet.accountAddress : "(no wallet yet)";
}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) node.append(child);
  return node;
}

function buildAgentCard(agentId, wallet) {
  const card = el("div", { className: "agent-card" });
  card.dataset.agent = agentId;

  const row = el("div", { className: "row" }, [el("span", { className: "agent-id", textContent: agentId })]);

  const addressEl = el("div", { className: "address", textContent: formatWallet(wallet) });
  const balanceEl = el("div", { className: "balance" });

  const walletBtn = el("button", {
    textContent: wallet ? "Refresh wallet" : "Create / assign wallet",
  });
  const balanceBtn = el("button", { className: "secondary", textContent: "Check USDC balance", disabled: !wallet });
  const payBtn = el("button", { textContent: "Pay x402 resource", disabled: !wallet });

  const actions = el("div", { className: "actions" }, [walletBtn, balanceBtn, payBtn]);
  actions.style.marginTop = "0.6rem";

  card.append(row, addressEl, balanceEl, actions);

  return { card, addressEl, balanceEl, walletBtn, balanceBtn, payBtn };
}

function wireAgentCard(refs, { walletPath, balancePath, payPath }) {
  const { addressEl, balanceEl, walletBtn, balanceBtn, payBtn } = refs;

  function setWallet(wallet) {
    addressEl.textContent = formatWallet(wallet);
    balanceBtn.disabled = !wallet;
    payBtn.disabled = !wallet;
    walletBtn.textContent = wallet ? "Refresh wallet" : "Create / assign wallet";
  }

  async function refreshBalance() {
    balanceEl.textContent = "checking balance…";
    try {
      const { balance } = await api("GET", balancePath);
      balanceEl.textContent = "";
      balanceEl.append(el("strong", { textContent: `${balance.formatted} USDC` }));
    } catch {
      balanceEl.textContent = "balance check failed (see log)";
    }
  }

  walletBtn.addEventListener("click", async () => {
    walletBtn.disabled = true;
    try {
      const { wallet } = await api("POST", walletPath);
      setWallet(wallet);
      await refreshBalance();
    } catch {
      // logged already
    } finally {
      walletBtn.disabled = false;
    }
  });

  balanceBtn.addEventListener("click", refreshBalance);

  payBtn.addEventListener("click", async () => {
    payBtn.disabled = true;
    try {
      await api("POST", payPath);
      await refreshBalance();
    } catch {
      // logged already
    } finally {
      payBtn.disabled = false;
    }
  });

  return { refreshBalance };
}

function addAgentCard(container, routePrefix, agentId, wallet) {
  const refs = buildAgentCard(agentId, wallet);
  container.append(refs.card);
  const controls = wireAgentCard(refs, {
    walletPath: `${routePrefix}/${agentId}/wallet`,
    balancePath: `${routePrefix}/${agentId}/balance`,
    payPath: `${routePrefix}/${agentId}/pay`,
  });
  return controls;
}

async function initRoute(routeName, containerId, newIdInputId, addButtonId) {
  const routePrefix = `/api/${routeName}/agents`;
  const container = document.getElementById(containerId);

  async function loadAll() {
    container.textContent = "";
    const { agents } = await api("GET", routePrefix);
    if (agents.length === 0) {
      container.append(el("p", { className: "empty-state", textContent: "No agents yet." }));
      return;
    }
    for (const agent of agents) {
      const controls = addAgentCard(container, routePrefix, agent.agentId, agent.wallet);
      if (agent.wallet) await controls.refreshBalance();
    }
  }

  await loadAll();

  const input = document.getElementById(newIdInputId);
  const addButton = document.getElementById(addButtonId);
  addButton.addEventListener("click", async () => {
    addButton.disabled = true;
    try {
      const agentId = input.value.trim() || undefined;
      const { agentId: createdId, wallet } = await api("POST", routePrefix, { agentId });
      input.value = "";
      container.querySelector(".empty-state")?.remove();
      const controls = addAgentCard(container, routePrefix, createdId, wallet);
      await controls.refreshBalance();
    } catch {
      // logged already
    } finally {
      addButton.disabled = false;
    }
  });
}

async function initConfig() {
  const configEl = document.getElementById("config");
  const config = await api("GET", "/api/config");
  configEl.textContent = "";
  configEl.append(
    "chain ",
    el("code", { textContent: String(config.chainId) }),
    " · rpc ",
    el("code", { textContent: config.rpcUrl }),
    " · resource ",
    el("code", { textContent: config.resourceUrl }),
  );
}

function initTabs() {
  const buttons = [...document.querySelectorAll(".tab-btn")];
  const panels = [...document.querySelectorAll(".tab-panel")];

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      for (const b of buttons) {
        const active = b === button;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", String(active));
      }
      for (const panel of panels) {
        panel.hidden = panel.id !== `tab-${button.dataset.tab}`;
        panel.classList.toggle("active", !panel.hidden);
      }
    });
  });
}

initTabs();
initConfig().catch(() => {});
initRoute("route1", "route1-agents", "route1-new-id", "route1-add").catch((error) =>
  logEvent("Failed to load Route 1 agents", false, error.message),
);
initRoute("route2", "route2-agents", "route2-new-id", "route2-add").catch((error) =>
  logEvent("Failed to load Route 2 agents", false, error.message),
);
