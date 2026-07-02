import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, emitNotificationsChanged, type Watchlist, type WatchItem } from "../api";
import { Empty } from "../components";

const WATCH_TYPES = ["company", "country", "industry", "executive", "keyword", "supply_chain"];

interface EditorItem extends WatchItem {
  uid: number;
}

export function WatchlistsPage() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [name, setName] = useState("My watchlist");
  const uid = useRef(1);
  const [items, setItems] = useState<EditorItem[]>([{ uid: 0, type: "country", value: "Taiwan" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setWatchlists(await api.watchlists());
  }, []);

  const guard = useCallback(
    async (fn: () => Promise<unknown>) => {
      setError(null);
      try {
        await fn();
        await reload();
        // Creating / re-checking / deleting a watchlist changes the alert feed —
        // tell the topbar bell to refresh its unread count.
        emitNotificationsChanged();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Something went wrong");
      }
    },
    [reload],
  );

  useEffect(() => {
    void guard(async () => undefined);
  }, [guard]);

  async function create(e: FormEvent) {
    e.preventDefault();
    const valid = items.filter((i) => i.value.trim()).map((i) => ({ type: i.type, value: i.value }));
    if (!name.trim() || valid.length === 0) return;
    setBusy(true);
    await guard(async () => {
      await api.createWatchlist(name.trim(), valid);
      setName("My watchlist");
      setItems([{ uid: uid.current++, type: "country", value: "Taiwan" }]);
    });
    setBusy(false);
  }

  const remove = (id: string) => guard(() => api.deleteWatchlist(id));
  const evaluate = (id: string) => guard(() => api.evaluateWatchlist(id));

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
            <div className="wrap" key={item.uid} style={{ gap: 8 }}>
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
          <button type="button" className="btn ghost" style={{ alignSelf: "start" }} onClick={() => setItems([...items, { uid: uid.current++, type: "keyword", value: "" }])}>
            + add condition
          </button>
          {error ? <div className="errbox">{error}</div> : null}
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

      <Link to="/alerts" className="card hover row-between" style={{ textDecoration: "none", alignItems: "center" }}>
        <div>
          <strong>Alerts</strong>
          <div className="faint" style={{ fontSize: 13, marginTop: 2 }}>
            Matches from these watchlists collect in your alerts feed — each linked to the source
            disclosure that triggered it.
          </div>
        </div>
        <span className="pill accent">Open alerts →</span>
      </Link>
    </div>
  );
}
