import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, emitNotificationsChanged, type Notification } from "../api";
import { Cat, Empty, ErrorView, Skeleton } from "../components";

type Filter = "all" | "unread";

export function AlertsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [watchlistCount, setWatchlistCount] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [notes, watchlists] = await Promise.all([api.notifications(), api.watchlists()]);
    setNotifications(notes);
    setWatchlistCount(watchlists.length);
  }, []);

  const guard = useCallback(
    async (fn: () => Promise<unknown>) => {
      setError(null);
      try {
        await fn();
        await reload();
        // Any mutation can change the unread count — refresh the topbar bell.
        emitNotificationsChanged();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Something went wrong");
      }
    },
    [reload],
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    reload()
      .catch((err: unknown) => {
        if (active) setError(err instanceof ApiError ? err.message : "Could not load alerts");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [reload]);

  async function checkForUpdates() {
    setChecking(true);
    setStatus(null);
    await guard(async () => {
      const res = await api.evaluateAllWatchlists();
      setStatus(
        res.notifications_created > 0
          ? `${res.notifications_created} new alert${res.notifications_created === 1 ? "" : "s"} from ${res.watchlists_evaluated} watchlist${res.watchlists_evaluated === 1 ? "" : "s"}.`
          : `Up to date — checked ${res.watchlists_evaluated} watchlist${res.watchlists_evaluated === 1 ? "" : "s"}, nothing new.`,
      );
    });
    setChecking(false);
  }

  const markAllRead = () => guard(() => api.markAllRead());
  const markRead = (id: string) => guard(() => api.markRead(id));

  const unread = notifications.filter((n) => !n.read).length;
  const shown = filter === "unread" ? notifications.filter((n) => !n.read) : notifications;

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Alerts</h1>
        <p className="sub">
          Every material change matched against your watchlists, in one place — each one linked to the
          source disclosure that triggered it. This is your "what changed since I last looked" feed.
        </p>
      </div>

      <div className="row-between" style={{ flexWrap: "wrap", gap: 12 }}>
        <div className="wrap" style={{ gap: 6 }} role="tablist" aria-label="Filter alerts">
          <button
            className={`pill${filter === "all" ? " accent" : ""}`}
            onClick={() => setFilter("all")}
            role="tab"
            aria-selected={filter === "all"}
          >
            All <span className="faint">{notifications.length}</span>
          </button>
          <button
            className={`pill${filter === "unread" ? " accent" : ""}`}
            onClick={() => setFilter("unread")}
            role="tab"
            aria-selected={filter === "unread"}
          >
            Unread <span className="faint">{unread}</span>
          </button>
        </div>
        <div className="wrap" style={{ gap: 8 }}>
          {status ? <span className="faint" style={{ fontSize: 12.5 }}>{status}</span> : null}
          <button className="btn" onClick={() => void checkForUpdates()} disabled={checking}>
            {checking ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Check for updates"}
          </button>
          <button className="btn ghost" onClick={() => void markAllRead()} disabled={unread === 0}>
            Mark all read
          </button>
        </div>
      </div>

      {error ? <ErrorView error={error} /> : null}

      {loading ? (
        <div className="list" aria-hidden="true">
          <Skeleton h={64} />
          <Skeleton h={64} />
          <Skeleton h={64} />
        </div>
      ) : watchlistCount === 0 ? (
        <Empty
          icon="🔔"
          title="No watchlists yet"
          hint={
            <>
              Alerts come from your watchlists.{" "}
              <Link to="/watchlists" className="mono">
                Create one →
              </Link>{" "}
              to start monitoring companies, countries, executives, and supply chains.
            </>
          }
        />
      ) : shown.length === 0 ? (
        <Empty
          icon="✓"
          title={filter === "unread" ? "No unread alerts" : "You're all caught up"}
          hint={
            filter === "unread"
              ? "Switch to All to review earlier alerts."
              : "Re-check for updates, or refine your watchlists to widen coverage."
          }
        />
      ) : (
        <div className="list">
          {shown.map((n) => (
            <div className="li" key={n.id} style={{ cursor: "default", opacity: n.read ? 0.6 : 1 }}>
              <div className="grow">
                <div className="wrap" style={{ gap: 8, marginBottom: 2 }}>
                  {!n.read ? (
                    <span
                      className="dot"
                      aria-label="unread"
                      style={{ display: "inline-block", width: 7, height: 7, borderRadius: 9, background: "var(--accent)" }}
                    />
                  ) : null}
                  <span style={{ fontWeight: 560 }}>{n.title}</span>
                  {n.category ? <Cat category={n.category} /> : null}
                  <span className="pill" title="The watchlist condition that matched">
                    <span className="faint">{n.watch_type.replace(/_/g, " ")}</span>&nbsp;{n.watch_value}
                  </span>
                </div>
                <div className="faint" style={{ fontSize: 13 }}>{n.detail}</div>
                {n.canonical_id ? (
                  <Link to={`/documents/${n.canonical_id}`} className="mono faint" style={{ fontSize: 11.5 }}>
                    ↳ source
                  </Link>
                ) : n.source_uri ? (
                  <span className="mono faint" style={{ fontSize: 11.5 }}>↳ {n.source_uri}</span>
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
  );
}
