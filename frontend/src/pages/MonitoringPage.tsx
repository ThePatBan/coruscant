import { api } from "../api";
import { Empty, ErrorView, Loading, sourceLabel } from "../components";
import { useAsync } from "../hooks";

function tierColor(tier: string): string {
  if (tier === "high") return "var(--good)";
  if (tier === "medium") return "var(--accent)";
  return "var(--text-faint)";
}

export function MonitoringPage() {
  const { data, error, loading } = useAsync(() => api.monitoring(), []);

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Source monitoring</h1>
        <p className="sub">
          Reliability per source — inherent authority blended with observed structure,
          completeness, and ingestion success. Higher-authority sources are weighted more.
        </p>
      </div>

      {loading ? <Loading label="Loading monitoring" /> : null}
      {error ? <ErrorView error={error} /> : null}
      {data && data.length === 0 ? <Empty title="No sources" /> : null}

      {data && data.length > 0 ? (
        <div className="list">
          {data.map((s) => (
            <div className="li" key={s.source_type} style={{ cursor: "default" }}>
              <div className="grow">
                <div style={{ fontWeight: 560 }}>{sourceLabel(s.source_type)}</div>
                <div className="faint" style={{ fontSize: 12.5 }}>
                  {s.document_count} docs · structure {(s.structure_score * 100).toFixed(0)}% ·
                  success {(s.success_rate * 100).toFixed(0)}%
                  {s.latest_published ? ` · latest ${s.latest_published}` : ""}
                </div>
              </div>
              <div style={{ width: 120 }}>
                <div
                  style={{
                    height: 6,
                    borderRadius: 999,
                    background: "var(--bg-elev-2)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${s.score}%`,
                      height: "100%",
                      background: tierColor(s.tier),
                    }}
                  />
                </div>
              </div>
              <span className="pill" style={{ color: tierColor(s.tier), minWidth: 84, justifyContent: "center" }}>
                {s.score} · {s.tier}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
