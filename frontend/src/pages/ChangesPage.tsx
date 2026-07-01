// What changed — the evidence-first insight surface. Master-detail: the master
// is the overnight change/risk/opportunity stream from the dashboard; the detail
// grounds each item in its source and enriches it with the real line-level
// change-detection (added/removed statements, each with an ↳ source) and any
// emerging signals for that company. Nothing is generated — every line is
// extracted from a periodic disclosure and traceable.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dashboard, type TimelineEvent } from "../api";
import { Empty, ErrorView, Loading, Skeleton } from "../components";
import { useAsync } from "../hooks";

type Dir = "risk" | "opp" | "event";
type Row = TimelineEvent & { dir: Dir; id: string };

const DIR_GLYPH: Record<Dir, string> = { risk: "▼", opp: "▲", event: "◍" };
const DIR_LABEL: Record<Dir, string> = { risk: "Risk", opp: "Opportunity", event: "Event" };
const catAttr = (c: string | null | undefined) => (c ?? "").toLowerCase().replace(/\s+/g, "_");
const rowId = (e: TimelineEvent) => `${e.canonical_id}|${e.section_title}|${e.title}`;

function unify(dash: Dashboard | null): Row[] {
  if (!dash) return [];
  const out: Row[] = [];
  const seen = new Set<string>();
  const add = (evts: TimelineEvent[], dir: Dir) => {
    for (const e of evts) {
      const id = rowId(e);
      if (seen.has(id)) continue;
      seen.add(id);
      out.push({ ...e, dir, id });
    }
  };
  add(dash.recent_risks, "risk");
  add(dash.recent_opportunities, "opp");
  add(dash.recent_events, "event");
  return out;
}

/** Detail pane: grounds the selected change and pulls its real change-detection. */
function ChangeDetail({ row }: { row: Row }) {
  const enrich = useAsync(
    () => Promise.all([api.companyChanges(row.company_slug), api.signals(row.company_slug)]),
    [row.company_slug],
  );
  const [changes, signals] = enrich.data ?? [null, null];
  const material = (changes ?? []).filter((cs) => cs.changes.length > 0);
  const diffs = material.flatMap((cs) => cs.changes).slice(0, 12);

  return (
    <div className="changes-detail">
      <div className="changes-dhead">
        <div className={`dp-glyph dir-${row.dir}`}>{DIR_GLYPH[row.dir]}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="changes-dmeta">
            <span className="dp-cat" data-c={catAttr(row.category)}>{(row.category || "general").replace(/_/g, " ")}</span>
            <span className="mono muted small">{row.company_slug.toUpperCase()}</span>
            <a className="src-link" href={row.source_uri} target="_blank" rel="noreferrer">
              <span className="arrow">↳</span> {row.section_title || "source"}
            </a>
          </div>
          <h1 className="changes-dtitle">{row.title || row.description}</h1>
        </div>
      </div>

      {row.description && row.description !== row.title ? (
        <p className="changes-ddesc">{row.description}</p>
      ) : null}

      <div className="dp-section">
        <div className="dp-section-head">
          <span className="kicker" style={{ color: "var(--evidence)" }}>Evidence · what changed</span>
          <span className="muted small">line-level change-detection for {row.company_slug.toUpperCase()}</span>
        </div>
        {enrich.loading ? (
          <Loading label="Reading disclosures" />
        ) : diffs.length === 0 ? (
          <div className="muted small">
            No line-level diff available — this company has a single ingested filing, so there is no prior
            period to compare against.
          </div>
        ) : (
          <div className="stack">
            {diffs.map((ch, i) => (
              <div className="changes-diff" key={i}>
                <span className={`changes-diffmark ${ch.kind}`}>{ch.kind === "added" ? "+" : "–"}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="changes-diff-stmt">{ch.statement}</div>
                  <div className="changes-diff-meta">
                    <span className="dp-cat" data-c={catAttr(ch.category)}>{(ch.category || "general").replace(/_/g, " ")}</span>
                    {ch.evidence?.source_uri ? (
                      <a className="src-link" href={ch.evidence.source_uri} target="_blank" rel="noreferrer">
                        <span className="arrow">↳</span> {ch.evidence.section_title || "source"}
                      </a>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
            {material.length > 0 ? (
              <div className="mono muted small">
                {material.reduce((a, cs) => a + cs.added_count, 0)} added ·{" "}
                {material.reduce((a, cs) => a + cs.removed_count, 0)} removed across {material.length} comparison
                {material.length === 1 ? "" : "s"}
              </div>
            ) : null}
          </div>
        )}
      </div>

      {signals && signals.length > 0 && (
        <div className="dp-section">
          <div className="dp-section-head">
            <span className="kicker" style={{ color: "var(--proxy)" }}>Emerging signals</span>
          </div>
          <div className="stack">
            {signals.map((s, i) => (
              <div className="changes-signal" key={i}>
                <div className="changes-signal-top">
                  <span className="changes-signal-l">{s.label}</span>
                  <span className="mono muted small">{s.direction} · strength {s.strength.toFixed(1)}</span>
                </div>
                <div className="muted small">{s.rationale}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="changes-actions">
        <a className="btn" href={row.source_uri} target="_blank" rel="noreferrer">Open document ↗</a>
        <Link className="btn ghost" to="/atlas">Open in Atlas ✦</Link>
        <span style={{ flex: 1 }} />
        <span className="mono muted small">
          Extractive change-detection over periodic disclosures — no generated numbers.
        </span>
      </div>
    </div>
  );
}

export function ChangesPage() {
  const dash = useAsync(() => api.dashboard(), []);
  const rows = useMemo(() => unify(dash.data), [dash.data]);

  const [filter, setFilter] = useState<"all" | Dir>("all");
  const [selId, setSelId] = useState<string | null>(null);

  const counts = useMemo(
    () => ({
      all: rows.length,
      risk: rows.filter((r) => r.dir === "risk").length,
      opp: rows.filter((r) => r.dir === "opp").length,
      event: rows.filter((r) => r.dir === "event").length,
    }),
    [rows],
  );
  const list = filter === "all" ? rows : rows.filter((r) => r.dir === filter);
  const selected = list.find((r) => r.id === selId) ?? list[0] ?? null;

  const filters: Array<[typeof filter, string, number]> = [
    ["all", "All", counts.all],
    ["risk", "Risk", counts.risk],
    ["opp", "Opportunity", counts.opp],
    ["event", "Events", counts.event],
  ];

  return (
    <div className="changes-page">
      <div className="page-head">
        <div className="kicker"><span className="idx">01</span> What changed · last period</div>
        <h1 style={{ marginTop: 6 }}>Insight detail — evidence first</h1>
        <div className="muted small" style={{ marginTop: 6 }}>
          Every change is extracted from a disclosure and carries its source. Select one to trace it to the
          line-level diff behind it.
        </div>
      </div>

      {dash.error ? (
        <ErrorView error={dash.error} />
      ) : (
        <>
          <div className="changes-split">
            {/* MASTER */}
            <section className="changes-master">
              <div className="changes-master-head">
                <div className="segmented">
                  {filters.map(([key, label, n]) => (
                    <button
                      key={key}
                      className={filter === key ? "active" : ""}
                      onClick={() => setFilter(key)}
                    >
                      {label} <span className="ct">{n}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="changes-list">
                {dash.loading ? (
                  <div className="stack gap" style={{ padding: 12 }}>
                    <Skeleton h={60} /><Skeleton h={60} /><Skeleton h={60} />
                  </div>
                ) : list.length === 0 ? (
                  <Empty icon="◍" title="Nothing in this filter" />
                ) : (
                  list.map((r) => {
                    const on = selected?.id === r.id;
                    return (
                      <button
                        key={r.id}
                        className={`changes-row${on ? " active" : ""}`}
                        onClick={() => setSelId(r.id)}
                      >
                        <div className={`dp-glyph sm dir-${r.dir}`}>{DIR_GLYPH[r.dir]}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="changes-row-title">{r.title || r.description}</div>
                          <div className="changes-row-meta">
                            <span className="dp-cat" data-c={catAttr(r.category)}>{(r.category || "general").replace(/_/g, " ")}</span>
                            <span className="mono muted small">{r.company_slug.toUpperCase()} · {DIR_LABEL[r.dir]}</span>
                          </div>
                        </div>
                        <span className="changes-row-chev mono">{on ? "›" : ""}</span>
                      </button>
                    );
                  })
                )}
              </div>
            </section>

            {/* DETAIL */}
            <section className="changes-detail-wrap">
              {dash.loading ? (
                <Skeleton h={260} />
              ) : selected ? (
                <ChangeDetail row={selected} key={selected.id} />
              ) : (
                <Empty icon="◍" title="No changes to show" />
              )}
            </section>
          </div>

          {/* live ticker */}
          {rows.length > 0 && (
            <div className="changes-ticker">
              <div className="changes-ticker-tag">
                <span className="dot" /> Live feed
              </div>
              <div className="changes-ticker-view">
                <div className="changes-ticker-track">
                  {[0, 1].map((dup) =>
                    rows.map((r, i) => (
                      <span className="changes-ticker-item" key={`${dup}-${i}`}>
                        <span className={`changes-ticker-dot dir-${r.dir}`} />
                        <span>{r.title || r.description}</span>
                        <span className="mono muted small">{r.company_slug.toUpperCase()}</span>
                      </span>
                    )),
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
