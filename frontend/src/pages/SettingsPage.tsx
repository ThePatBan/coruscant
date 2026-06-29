import { type FormEvent, useCallback, useEffect, useState } from "react";
import { api, type ApiKey, type CurrentUser } from "../api";
import { Empty, Loading } from "../components";
import { useAsync } from "../hooks";

export function SettingsPage() {
  const me = useAsync<CurrentUser>(() => api.me(), []);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState("My integration");
  const [secret, setSecret] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setKeys(await api.apiKeys());
    setLoading(false);
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const created = await api.createApiKey(name.trim());
    setSecret(created.secret);
    await reload();
  }

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Settings</h1>
        <p className="sub">Your account and programmatic access. API keys authenticate the public API.</p>
      </div>

      <div className="card stack gap-sm">
        <h2>Account</h2>
        {me.data ? (
          <div className="wrap">
            <span className="pill accent">{me.data.email}</span>
            <span className="pill">role: {me.data.role}</span>
          </div>
        ) : (
          <Loading label="Loading account" />
        )}
        <a className="mono faint" href="/api/docs" target="_blank" rel="noreferrer" style={{ fontSize: 12.5 }}>
          Public API docs (OpenAPI) ↗
        </a>
      </div>

      <div className="card stack gap">
        <h2>API keys</h2>
        <p className="faint" style={{ fontSize: 13 }}>
          Use a key as <span className="mono">X-API-Key</span> to call the API programmatically.
        </p>
        {secret ? (
          <div className="answer" style={{ borderLeftColor: "var(--good)" }}>
            <div className="answer-label" style={{ color: "var(--good)" }}>New key — copy it now, shown once</div>
            <div className="mono" style={{ wordBreak: "break-all" }}>{secret}</div>
          </div>
        ) : null}
        <form className="wrap" style={{ gap: 8 }} onSubmit={create}>
          <input className="input" style={{ flex: 1 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="Key name" />
          <button className="btn" type="submit">Create key</button>
        </form>
        {loading ? <Loading label="Loading keys" /> : null}
        {!loading && keys.length === 0 ? <Empty title="No API keys" /> : null}
        {keys.length > 0 ? (
          <div className="list">
            {keys.map((k) => (
              <div className="li" key={k.id} style={{ cursor: "default" }}>
                <div className="grow">
                  <div style={{ fontWeight: 560 }}>{k.name}</div>
                  <div className="mono faint" style={{ fontSize: 12 }}>{k.display}</div>
                </div>
                <button
                  className="btn ghost"
                  style={{ padding: "5px 10px" }}
                  onClick={async () => {
                    await api.revokeApiKey(k.id);
                    await reload();
                  }}
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
