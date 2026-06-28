import { Link } from "react-router-dom";
import { api, type TimelineEvent } from "../api";
import { Cat, docTypeLabel, Empty, ErrorView, Loading } from "../components";
import { useAsync } from "../hooks";

function EventRow({ event }: { event: TimelineEvent }) {
  return (
    <Link to={`/documents/${event.canonical_id}`} className="tl-item" style={{ display: "block" }}>
      <div className="wrap" style={{ gap: 8, marginBottom: 2 }}>
        <Cat category={event.category} />
        <span className="when">{event.occurred_at ?? "—"}</span>
      </div>
      <div style={{ fontSize: 14, fontWeight: 540 }}>{event.title}</div>
    </Link>
  );
}

export function DashboardPage() {
  const { data, error, loading } = useAsync(() => api.dashboard(), []);

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Dashboard</h1>
        <p className="sub">
          What changed across the monitored universe — material changes, latest disclosures, and
          the risk and opportunity signals extracted from them.
        </p>
      </div>

      {loading ? <Loading label="Loading dashboard" /> : null}
      {error ? <ErrorView error={error} /> : null}

      {data ? (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="num">{data.companies}</div>
              <div className="lbl">Companies monitored</div>
            </div>
            <div className="stat">
              <div className="num">{data.documents}</div>
              <div className="lbl">Documents processed</div>
            </div>
            <div className="stat">
              <div className="num">{data.events}</div>
              <div className="lbl">Events extracted</div>
            </div>
            <div className="stat alert">
              <div className="num">{data.material_changes}</div>
              <div className="lbl">Material changes detected</div>
            </div>
          </div>

          <div className="grid cols-2">
            <div className="stack gap">
              <h2>Latest disclosures</h2>
              {data.latest_documents.length === 0 ? (
                <Empty title="No documents yet" />
              ) : (
                <div className="list">
                  {data.latest_documents.map((d) => (
                    <Link to={`/documents/${d.canonical_id}`} className="li" key={d.canonical_id}>
                      <div className="grow">
                        <div className="truncate" style={{ fontWeight: 560 }}>
                          {d.title ?? "Untitled"}
                        </div>
                        <div className="faint" style={{ fontSize: 12.5 }}>
                          {d.published_at ?? "—"}
                        </div>
                      </div>
                      <span className="badge">{docTypeLabel(d.document_type)}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>

            <div className="stack gap">
              <h2>Recent events</h2>
              {data.recent_events.length === 0 ? (
                <Empty title="No events yet" />
              ) : (
                <div className="card">
                  <div className="timeline">
                    {data.recent_events.map((e, i) => (
                      <EventRow event={e} key={`${e.canonical_id}-${i}`} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="grid cols-2">
            <SignalCard title="Risk signals" icon="⚠" events={data.recent_risks} empty="No risk signals" />
            <SignalCard
              title="Opportunity signals"
              icon="↗"
              events={data.recent_opportunities}
              empty="No opportunity signals"
            />
          </div>
        </>
      ) : null}
    </div>
  );
}

function SignalCard({
  title,
  icon,
  events,
  empty,
}: {
  title: string;
  icon: string;
  events: TimelineEvent[];
  empty: string;
}) {
  return (
    <div className="stack gap">
      <h2>
        {icon} {title}
      </h2>
      {events.length === 0 ? (
        <Empty title={empty} />
      ) : (
        <div className="card stack gap-sm">
          {events.map((e, i) => (
            <Link
              to={`/documents/${e.canonical_id}`}
              key={`${e.canonical_id}-${i}`}
              className="stack"
              style={{ gap: 4, padding: "6px 0", borderTop: i ? "1px dashed var(--border)" : "none" }}
            >
              <div className="wrap" style={{ gap: 8 }}>
                <Cat category={e.category} />
                <span className="when">{e.occurred_at ?? "—"}</span>
              </div>
              <div style={{ fontSize: 14 }}>{e.description}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
