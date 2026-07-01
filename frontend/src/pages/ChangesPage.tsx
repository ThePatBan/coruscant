// What changed — the evidence-first insight surface (design-pack Screen 2).
// Master-detail: the master is the overnight risk/opportunity/event stream from
// the dashboard; the detail is the editorial read — why it matters (a grounded
// synthesis, not hand-written copy), the tinted line-level evidence diff (each
// with an ↳ source), the connected entities from the graph, and how it was
// derived. Nothing generated: every line is extracted from a disclosure.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type ChangeSet,
  type Dashboard,
  type EntityProfile,
  type Relationship,
  type TimelineEvent,
} from "../api";
import { Empty, ErrorView, Loading, Skeleton } from "../components";
import { useAsync } from "../hooks";

type Dir = "risk" | "opp" | "event";
type Row = TimelineEvent & { dir: Dir; id: string };

const DIR_GLYPH: Record<Dir, string> = { risk: "▼", opp: "▲", event: "◍" };
const DIR_LABEL: Record<Dir, string> = { risk: "Risk", opp: "Opportunity", event: "Event" };
const catAttr = (c: string | null | undefined) => (c ?? "").toLowerCase().replace(/\s+/g, "_");
const clean = (c: string | null | undefined) => (c || "general").replace(/_/g, " ");
const rowId = (e: TimelineEvent) => `${e.canonical_id}|${e.section_title}|${e.title}`;

const KIND_COLOR: Record<string, string> = {
  Company: "var(--accent)",
  Person: "var(--proxy)",
  Subsidiary: "var(--evidence)",
  Supplier: "var(--evidence)",
  Country: "var(--rel-country)",
  Technology: "var(--rel-tech)",
  Commodity: "var(--cat-supply)",
};

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

function whyItMatters(row: Row, added: number, removed: number): string {
  const co = row.company_slug.toUpperCase();
  const cat = clean(row.category);
  const src = (row.source_type || "filing").replace(/_/g, " ");
  if (added + removed === 0) {
    return `${co} surfaced a ${cat} item in its latest ${src}. No prior-period comparison is available, so read it as a point-in-time disclosure rather than a trend.`;
  }
  const lead =
    row.dir === "opp"
      ? "a potential upside to watch"
      : row.dir === "risk"
        ? "a shift to price as risk"
        : "a change to note";
  return `${co} rewrote its ${cat} disclosure versus the prior ${src} — ${added} statement${added === 1 ? "" : "s"} added, ${removed} removed. In the company's own words, that reads as ${lead}; trace the diff below before acting.`;
}

/** Editorial detail pane, grounded and enriched from real change-detection. */
function ChangeDetail({ row }: { row: Row }) {
  const enrich = useAsync(
    () =>
      Promise.all([
        api.companyChanges(row.company_slug),
        api.entity("Company", row.company_slug).catch(() => null),
      ]),
    [row.company_slug],
  );
  const [changes, profile] = (enrich.data ?? [null, null]) as [ChangeSet[] | null, EntityProfile | null];
  const material = (changes ?? []).filter((cs) => cs.changes.length > 0);
  const added = material.reduce((a, cs) => a + cs.added_count, 0);
  const removed = material.reduce((a, cs) => a + cs.removed_count, 0);
  const diffs = material.flatMap((cs) => cs.changes).slice(0, 10);
  const isMaterial = material.length > 0;

  // connected entities from the graph — deduped by key, a few typed chips
  const connected: Relationship[] = [];
  const seenKeys = new Set<string>();
  for (const r of profile?.relationships ?? []) {
    if (seenKeys.has(r.other.key)) continue;
    seenKeys.add(r.other.key);
    connected.push(r);
    if (connected.length >= 6) break;
  }

  const evTint = row.dir === "opp" ? "opp" : row.dir === "risk" ? "risk" : "neutral";

  return (
    <div className="changes-detail">
      {/* header */}
      <div className="changes-dhead">
        <div className={`dp-glyph dir-${row.dir}`}>{DIR_GLYPH[row.dir]}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="changes-dmeta">
            <span className="dp-cat" data-c={catAttr(row.category)}>{clean(row.category)}</span>
            {isMaterial ? <span className="changes-material">material</span> : null}
            <a className="src-link" href={row.source_uri} target="_blank" rel="noreferrer">
              <span className="arrow">↳</span> {(row.source_type || "source").replace(/_/g, " ")}
              {row.section_title ? ` · ${row.section_title}` : ""}
            </a>
          </div>
          <h1 className="changes-dtitle">{row.title || row.description}</h1>
          {row.description && row.description !== row.title ? (
            <p className="changes-ddesc">{row.description}</p>
          ) : null}
        </div>
      </div>

      {/* why it matters */}
      <div className="dp-section">
        <div className="kicker" style={{ marginBottom: 10 }}>Why it matters to your book</div>
        {enrich.loading ? (
          <Skeleton h={44} />
        ) : (
          <p className="changes-why">{whyItMatters(row, added, removed)}</p>
        )}
        <div className="changes-affected">
          <span className="changes-affected-l">Holdings affected</span>
          <Link className="changes-affected-chip" to="/atlas">
            <span className="dot" style={{ width: 6, height: 6, background: "var(--accent)", boxShadow: "none" }} />
            {row.company_slug.toUpperCase()}
          </Link>
        </div>
      </div>

      {/* evidence diff */}
      <div className="dp-section">
        <div className="dp-section-head">
          <span className="kicker" style={{ color: "var(--evidence)" }}>Evidence · the source text this rests on</span>
        </div>
        {enrich.loading ? (
          <Loading label="Reading disclosures" />
        ) : diffs.length === 0 ? (
          <div className={`changes-ev changes-ev-${evTint}`}>
            <p style={{ margin: 0 }}>{row.description || row.title}</p>
            <a className="src-link" style={{ marginTop: 10 }} href={row.source_uri} target="_blank" rel="noreferrer">
              <span className="arrow">↳</span> open document →
            </a>
            <div className="mono muted small" style={{ marginTop: 6 }}>
              No line-level diff — a single ingested filing, so there is no prior period to compare.
            </div>
          </div>
        ) : (
          <div className="stack">
            {diffs.map((ch, i) => (
              <div className={`changes-diff ${ch.kind}`} key={i}>
                <span className={`changes-diffmark ${ch.kind}`}>{ch.kind === "added" ? "+" : "–"}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="changes-diff-stmt">{ch.statement}</div>
                  <div className="changes-diff-meta">
                    <span className="dp-cat" data-c={catAttr(ch.category)}>{clean(ch.category)}</span>
                    {ch.evidence?.source_uri ? (
                      <a className="src-link" href={ch.evidence.source_uri} target="_blank" rel="noreferrer">
                        <span className="arrow">↳</span> {ch.evidence.section_title || "source"} · open →
                      </a>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
            <div className="mono muted small">
              {added} added · {removed} removed across {material.length} comparison{material.length === 1 ? "" : "s"}
            </div>
          </div>
        )}
      </div>

      {/* connected entities */}
      {connected.length > 0 && (
        <div className="dp-section">
          <div className="dp-section-head">
            <span className="kicker">Connected entities</span>
            <Link className="btn ghost" to="/atlas">Open in Atlas ✦ →</Link>
          </div>
          <div className="changes-chips">
            {connected.map((r, i) => (
              <span className="changes-echip" key={`${r.other.key}-${i}`}>
                <span className="dot" style={{ width: 7, height: 7, background: KIND_COLOR[r.other.kind] || "var(--text-faint)", boxShadow: "none" }} />
                <strong>{r.other.name}</strong>
                <span className="muted small">{r.other.kind}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* how derived */}
      <div className="changes-derived">
        <div style={{ flex: 1, minWidth: 220 }}>
          <span className="changes-derived-l">How derived</span>
          <span className="changes-derived-t">
            Extractive change-detection over periodic disclosures — no generated numbers.{" "}
            {isMaterial ? "Diff is confirmed against the prior filing." : "Point-in-time extraction; awaiting a prior period."}
          </span>
        </div>
        <a className="btn" href={row.source_uri} target="_blank" rel="noreferrer">Trace to source →</a>
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
    <div className="changes-page spatial-page">
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
            <section className="changes-master">
              <div className="changes-master-head">
                <div className="segmented">
                  {filters.map(([key, label, n]) => (
                    <button key={key} className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>
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
                      <button key={r.id} className={`changes-row${on ? " active" : ""}`} onClick={() => setSelId(r.id)}>
                        <div className={`dp-glyph sm dir-${r.dir}`}>{DIR_GLYPH[r.dir]}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="changes-row-title">{r.title || r.description}</div>
                          <div className="changes-row-meta">
                            <span className="dp-cat" data-c={catAttr(r.category)}>{clean(r.category)}</span>
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
