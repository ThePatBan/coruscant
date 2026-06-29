import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Notification, type Watchlist, type WatchItem } from "../api";
import { Cat, Empty } from "../components";

const WATCH_TYPES = ["company", "country", "industry", "executive", "keyword", "supply_chain"];

export function WatchlistsPage() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [name, setName] = useState("My watchlist");
  const [items, setItems] = useState<WatchItem[]>([{ type: "country", value: "Taiwan" }]);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const [wl, notes] = await Promise.all([api.watchlists(), api.notifications()]);
    setWatchlists(wl);
    setNotifications(notes);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function create(e: FormEvent) {
    e.preventDefault();
    const valid = items.filter((i) => i.value.trim());
    if (!name.trim() || valid.length === 0) return;
    setBusy(true);
    try {
      await api.createWatchlist(name.trim(), valid);
      setName("My watchlist");
      setItems([{ type: "country", value: "Taiwan" }]);
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    await api.deleteWatchlist(id);
    await reload();
  }
  async function evaluate(id: string) {
    await api.evaluateWatchlist(id);
    await reload();
  }
  async function markRead(id: string) {
    await api.markRead(id);
    await reload();
  }

  const unread = notifications.filter((n) => !n.read).length;

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Watchlists</h1>
        <p className="sub">
          Monitor companies, countries, executives, industries, and supply chains. When something
          materially changes, you get a notification — linked to its source.
        </p>
      </div>

      <div className="grid cols-2">
        <form className="card stack gap" onSubmit={create}>
          <h2>New watchlist</h2>
          <div className="field">
            <label>Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {items.map((item, i) => (
            <div className="wrap" key={i} style={{ gap: 8 }}>
              <select
                className="input"
                value={item.type}
                onChange={(e) =>
                  setItems(items.map((it, j) => (j === i ? { ...it, type: e.target.value } : it)))
                }
              >
                {WATCH_TYPES.map((t) => (
                  <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                ))}
              </select>
              <input
                className="input"
                style={{ flex: 1 }}
                placeholder="value (e.g. Taiwan, apple, guidance)"
                value={item.value}
                onChange={(e) =>
                  setItems(items.map((it, j) => (j === i ? { ...it, value: e.target.value } : it)))
                }
              />
              {items.length > 1 ? (
                <button type="button" className="btn ghost" onClick={() => setItems(items.filter((_, j) => j !== i))}>
                  −
                </button>
              ) : null}
            </div>
          ))}
          <button type="button" className="btn ghost" style={{ alignSelf: "start" }} onClick={() => setItems([...items, { type: "keyword", value: "" }])}>
            + add condition
          </button>
          <button className="btn" type="submit" disabled={busy}>
            {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Create & evaluate"}
          </button>
        </form>

        <div className="stack gap">
          <div className="row-between">
            <h2>Your watchlists</h2>
            <span className="badge">{watchlists.length}</span>
          </div>
          {watchlists.length === 0 ? (
            <Empty title="No watchlists yet" hint="Create one to start monitoring." />
          ) : (
            watchlists.map((wl) => (
              <div className="card stack gap-sm" key={wl.id}>
                <div className="row-between">
                  <strong>{wl.name}</strong>
                  <div className="wrap" style={{ gap: 6 }}>
                    <button className="btn ghost" style={{ padding: "5px 10px" }} onClick={() => void evaluate(wl.id)}>
                      Re-check
                    </button>
                    <button className="btn ghost" style={{ padding: "5px 10px" }} onClick={() => void remove(wl.id)}>
                      Delete
                    </button>
                  </div>
                </div>
                <div className="wrap">
                  {wl.items.map((it, i) => (
                    <span className="pill" key={i}>
                      <span className="faint">{it.type.replace(/_/g, " ")}</span>&nbsp;{it.value}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="stack gap">
        <div className="row-between">
          <h2>Notifications</h2>
          {unread > 0 ? <span className="pill evidence">{unread} unread</span> : null}
        </div>
        {notifications.length === 0 ? (
          <Empty icon="🔔" title="No notifications" hint="Create a watchlist to generate alerts." />
        ) : (
          <div className="list">
            {notifications.map((n) => (
              <div className="li" key={n.id} style={{ cursor: "default", opacity: n.read ? 0.6 : 1 }}>
                <div className="grow">
                  <div className="wrap" style={{ gap: 8, marginBottom: 2 }}>
                    {!n.read ? <span className="dot" style={{ display: "inline-block", width: 7, height: 7, borderRadius: 9, background: "var(--accent)" }} /> : null}
                    <span style={{ fontWeight: 560 }}>{n.title}</span>
                    {n.category ? <Cat category={n.category} /> : null}
                  </div>
                  <div className="faint" style={{ fontSize: 13 }}>{n.detail}</div>
                  {n.canonical_id ? (
                    <Link to={`/documents/${n.canonical_id}`} className="mono faint" style={{ fontSize: 11.5 }}>
                      ↳ source
                    </Link>
                  ) : null}
                </div>
                {!n.read ? (
                  <button className="btn ghost" style={{ padding: "5px 10px" }} onClick={() => void markRead(n.id)}>
                    Mark read
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
