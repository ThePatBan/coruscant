import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Customer,
  type LLMConfig,
  type LLMProviderIn,
  type LLMRoute,
  type LLMTestResult,
} from "../api";
import { useAsync } from "../hooks";
import { Loading } from "../components";

// The admin console — a single pane for running the business: route each task
// tier to a model (local Gemma for bulk work, Opus for the hard reasoning) and
// see who's using the platform.
export function AdminPage() {
  const { data, error, loading } = useAsync(() => api.adminLLM(), []);
  if (loading || (!data && !error)) return <Loading label="Loading admin console" />;
  if (error || !data) {
    return (
      <div className="errbox" role="alert" style={{ margin: 24 }}>
        {typeof error === "string" && error.toLowerCase().includes("admin")
          ? "This page requires an admin account."
          : "Could not load the admin console."}
      </div>
    );
  }
  return <AdminConsole initial={data} />;
}

function AdminConsole({ initial }: { initial: LLMConfig }) {
  const [providers, setProviders] = useState<Record<string, LLMProviderIn>>(() =>
    Object.fromEntries(
      Object.entries(initial.providers).map(([key, p]) => [
        key,
        { kind: p.kind, base_url: p.base_url, label: p.label, api_key: null },
      ]),
    ),
  );
  const [routes, setRoutes] = useState<Record<string, LLMRoute>>(() => ({ ...initial.routes }));
  const [hasKey, setHasKey] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(Object.entries(initial.providers).map(([k, p]) => [k, p.has_key])),
  );
  const [available, setAvailable] = useState<Record<string, boolean>>(initial.available);
  const [tests, setTests] = useState<Record<string, LLMTestResult | "pending">>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [newName, setNewName] = useState("");
  const providerKeys = useMemo(() => Object.keys(providers), [providers]);

  const setRoute = (tier: string, patch: Partial<LLMRoute>) =>
    setRoutes((r) => ({ ...r, [tier]: { ...r[tier], ...patch } }));
  const setProvider = (key: string, patch: Partial<LLMProviderIn>) =>
    setProviders((p) => ({ ...p, [key]: { ...p[key], ...patch } }));

  const addProvider = () => {
    const id = newName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    if (!id || providers[id]) return;
    const kind = /anthropic|claude|haiku|opus|sonnet/.test(id) ? "anthropic" : "openai";
    const base_url = kind === "anthropic" ? "https://api.anthropic.com" : "https://api.openai.com/v1";
    setProviders((p) => ({ ...p, [id]: { kind, base_url, label: newName.trim(), api_key: "" } }));
    setHasKey((h) => ({ ...h, [id]: false }));
    setNewName("");
  };
  const removeProvider = (key: string) => {
    if (Object.values(routes).some((r) => r.provider === key)) return; // in use — unroute first
    setProviders((p) => {
      const { [key]: _drop, ...rest } = p;
      return rest;
    });
  };

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const next = await api.adminLLMSave({ providers, routes });
      setAvailable(next.available);
      setHasKey(Object.fromEntries(Object.entries(next.providers).map(([k, p]) => [k, p.has_key])));
      // Clear typed keys (they're stored now; we never read them back).
      setProviders((p) =>
        Object.fromEntries(Object.entries(p).map(([k, v]) => [k, { ...v, api_key: null }])),
      );
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  const runTest = async (tier: string) => {
    setTests((t) => ({ ...t, [tier]: "pending" }));
    const result = await api.adminLLMTest(tier).catch(
      (e): LLMTestResult => ({ ok: false, tier, error: e instanceof Error ? e.message : "failed" }),
    );
    setTests((t) => ({ ...t, [tier]: result }));
  };

  return (
    <div className="admin">
      <header className="page-head">
        <h1>Admin console</h1>
        <p className="faint">A single pane for running the business — model routing and your customers.</p>
      </header>

      <section className="card">
        <div className="card-head">
          <h2>Model routing</h2>
          <button className="btn" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
        <p className="faint card-sub">
          Each task tier runs on the model you route it to. Use a cheap/local model for bulk work and reserve the
          most capable model for demanding synthesis.
        </p>

        <div className="tier-grid">
          {initial.tiers.map((tier) => {
            const route = routes[tier];
            const ok = available[tier];
            const test = tests[tier];
            return (
              <div className="tier-row" key={tier}>
                <div className="tier-id">
                  <span className={`avail-dot ${ok ? "on" : "off"}`} title={ok ? "Ready" : "No key / unreachable"} />
                  <div>
                    <div className="tier-name">{tier}</div>
                    <div className="faint tier-hint">{initial.tier_hints[tier]}</div>
                  </div>
                </div>
                <div className="tier-controls">
                  <select value={route?.provider} onChange={(e) => setRoute(tier, { provider: e.target.value })}>
                    {providerKeys.map((k) => (
                      <option key={k} value={k}>
                        {providers[k].label || k}
                      </option>
                    ))}
                  </select>
                  <input
                    className="model-input"
                    value={route?.model ?? ""}
                    placeholder="model id"
                    onChange={(e) => setRoute(tier, { model: e.target.value })}
                  />
                  <button className="btn ghost" onClick={() => runTest(tier)}>
                    Test
                  </button>
                </div>
                {test ? (
                  <div className={`tier-test ${test === "pending" ? "" : test.ok ? "ok" : "bad"}`}>
                    {test === "pending"
                      ? "Testing…"
                      : test.ok
                        ? `✓ ${test.model} replied in ${test.latency_ms}ms`
                        : `✕ ${test.error}`}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Providers &amp; keys</h2>
          {saved ? <span className="pill" style={{ color: "var(--good)" }}>Saved</span> : null}
        </div>
        <p className="faint card-sub">
          Keys are stored server-side and never sent back to the browser. Leave a key blank to keep the current one.
        </p>
        <div className="provider-list">
          {providerKeys.map((key) => {
            const p = providers[key];
            const inUse = Object.values(routes).some((r) => r.provider === key);
            return (
              <div className="provider-row" key={key}>
                <div className="provider-name">{p.label || key}</div>
                <select value={p.kind} onChange={(e) => setProvider(key, { kind: e.target.value })}>
                  <option value="openai">OpenAI-compatible</option>
                  <option value="anthropic">Anthropic</option>
                </select>
                <input
                  className="base-input"
                  value={p.base_url}
                  onChange={(e) => setProvider(key, { base_url: e.target.value })}
                  placeholder="base URL"
                />
                <input
                  type="password"
                  className="key-input"
                  value={p.api_key ?? ""}
                  onChange={(e) => setProvider(key, { api_key: e.target.value })}
                  placeholder={hasKey[key] ? "•••••••• (set — leave blank to keep)" : "no key set"}
                />
                <button
                  className="prov-x"
                  onClick={() => removeProvider(key)}
                  disabled={inUse}
                  title={inUse ? "Routed to a tier — unroute it first" : "Remove provider"}
                  aria-label="Remove provider"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
        <div className="add-provider">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addProvider()}
            placeholder="New slot name (e.g. Anthropic — Sonnet, or a 2nd local model)"
          />
          <button className="btn ghost" onClick={addProvider} disabled={!newName.trim()}>
            + Add provider
          </button>
        </div>
      </section>

      <CustomersCard />
    </div>
  );
}

function CustomersCard() {
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  useEffect(() => {
    api.adminCustomers().then(setCustomers).catch(() => setCustomers([]));
  }, []);
  return (
    <section className="card">
      <div className="card-head">
        <h2>Customers</h2>
        {customers ? <span className="pill">{customers.length}</span> : null}
      </div>
      {!customers ? (
        <Loading label="Loading customers" />
      ) : customers.length === 0 ? (
        <p className="faint">No customers yet.</p>
      ) : (
        <table className="tbl">
          <thead>
            <tr>
              <th>Email</th>
              <th>Role</th>
              <th>Joined</th>
              <th>API calls</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((c) => (
              <tr key={c.email}>
                <td>{c.email}</td>
                <td>
                  <span className={`pill ${c.role === "admin" ? "accent" : ""}`}>{c.role}</span>
                </td>
                <td className="faint">{c.created_at ? c.created_at.slice(0, 10) : "—"}</td>
                <td>{c.api_calls.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
