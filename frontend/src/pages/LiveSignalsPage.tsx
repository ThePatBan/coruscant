// Live Signals (design-pack Screen 3) — where the book is moving and why it
// touches you. Real per-company emerging signals (/signals across the 53
// holdings) geo-placed by HQ country onto an interactive globe; the rail lists
// them, filterable by kind and by feed topic (GICS sector). Selecting a signal
// in the rail eases the globe to it, and vice-versa. News layers in when the
// GDELT feed is connected; when off it's a labelled stub, never fabricated.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type NewsFeed } from "../api";
import { Empty, ErrorView, Skeleton } from "../components";
import { coordForCompany } from "../geo";
import { useAsync } from "../hooks";
import { SignalsGlobe, type GlobeSignal } from "../SignalsGlobe";

type Dir = "risk" | "opp" | "event";
const GLYPH: Record<Dir, string> = { risk: "▼", opp: "▲", event: "◍" };
const DIR_LABEL: Record<Dir, string> = { risk: "Risk", opp: "Opportunity", event: "Signal" };

interface Sig {
  id: string;
  slug: string;
  company: string;
  sector: string;
  dir: Dir;
  label: string;
  why: string;
  strength: number;
  country: string | null;
  lat?: number;
  lon?: number;
  source?: string | null;
  section?: string | null;
}

interface LoadOut {
  sigs: Sig[];
  news: NewsFeed | null;
  sectors: string[];
}

function dirOf(type: string): Dir {
  const t = type.toLowerCase();
  if (t.includes("opportun")) return "opp";
  if (t.includes("risk")) return "risk";
  return "event";
}

async function loadSignals(): Promise<LoadOut> {
  const [gics, news] = await Promise.all([api.gicsBreakdown(), api.news().catch(() => null)]);
  const roster = new Map<string, { name: string; sector: string }>();
  for (const s of gics) for (const sub of s.sub_industries) for (const co of sub.companies) {
    if (!roster.has(co.key)) roster.set(co.key, { name: co.name, sector: s.sector });
  }
  const slugs = [...roster.keys()];
  const arrays = await Promise.all(slugs.map((sl) => api.signals(sl).catch(() => [])));
  const sigs: Sig[] = [];
  slugs.forEach((sl, i) => {
    const co = roster.get(sl)!;
    const coord = coordForCompany(sl);
    for (const sig of arrays[i]) {
      sigs.push({
        id: `${sl}-${sigs.length}`,
        slug: sl,
        company: co.name,
        sector: co.sector,
        dir: dirOf(sig.type),
        label: sig.label,
        why: sig.rationale,
        strength: sig.strength,
        country: coord?.country ?? null,
        lat: coord?.lat,
        lon: coord?.lon,
        source: sig.evidence?.[0]?.source_uri ?? null,
        section: sig.evidence?.[0]?.section_title ?? null,
      });
    }
  });
  // strongest first
  sigs.sort((a, b) => b.strength - a.strength);
  const sectors = [...new Set(sigs.map((s) => s.sector))];
  return { sigs, news: news ?? null, sectors };
}

export function LiveSignalsPage() {
  const load = useAsync(loadSignals, []);
  const data = load.data;

  const [filter, setFilter] = useState<"all" | "changes" | "news">("all");
  const [topicsOff, setTopicsOff] = useState<Record<string, boolean>>({});
  const [selId, setSelId] = useState<string | null>(null);

  const newsOn = !!data?.news?.connected;

  const shown = useMemo(() => {
    if (!data) return [];
    return data.sigs.filter((s) => !topicsOff[s.sector] && (filter === "all" || filter === "changes"));
  }, [data, filter, topicsOff]);

  const located = useMemo<GlobeSignal[]>(
    () =>
      shown
        .filter((s) => s.lat != null && s.lon != null)
        .map((s) => ({ id: s.id, lat: s.lat!, lon: s.lon!, cat: s.dir, label: s.company })),
    [shown],
  );

  const selected = shown.find((s) => s.id === selId) ?? shown[0] ?? null;
  const locatedCount = data ? data.sigs.filter((s) => s.lat != null).length : 0;

  return (
    <div className="ls-page spatial-page">
      <div className="page-head">
        <div className="kicker"><span className="idx">03</span> Live signals</div>
        <h1 style={{ marginTop: 6 }}>Where it's happening — and why it touches your book</h1>
        <div className="muted small" style={{ marginTop: 6 }}>
          Emerging signals across your holdings, geo-placed by HQ. {locatedCount} located · selecting a signal
          eases the globe to it.
        </div>
      </div>

      {load.error ? (
        <ErrorView error={load.error} />
      ) : (
        <>
          <div className="ls-split">
            {/* RAIL */}
            <aside className="ls-rail">
              <div className="ls-rail-head">
                <div className="kicker">Signals · touching your book</div>
                <span className="mono muted">{shown.length}</span>
              </div>
              <div className="segmented ls-filters">
                {(
                  [
                    ["all", "All", data?.sigs.length ?? 0],
                    ["changes", "Signals", data?.sigs.length ?? 0],
                    ["news", "News", newsOn ? data?.news?.articles.length ?? 0 : 0],
                  ] as const
                ).map(([k, label, n]) => (
                  <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>
                    {label} <span className="ct">{n}</span>
                  </button>
                ))}
              </div>
              {data && data.sectors.length > 0 ? (
                <div className="ls-topics">
                  <span className="mono ls-topics-l">Feed</span>
                  {data.sectors.map((sec) => {
                    const on = !topicsOff[sec];
                    return (
                      <button
                        key={sec}
                        className={`ls-topic${on ? " on" : ""}`}
                        onClick={() => setTopicsOff((o) => ({ ...o, [sec]: on }))}
                      >
                        {sec}
                      </button>
                    );
                  })}
                </div>
              ) : null}

              <div className="ls-list">
                {load.loading ? (
                  <div className="stack gap" style={{ padding: 10 }}>
                    <Skeleton h={52} /><Skeleton h={52} /><Skeleton h={52} /><Skeleton h={52} />
                  </div>
                ) : filter === "news" ? (
                  newsOn && data?.news?.articles.length ? (
                    data.news.articles.slice(0, 20).map((a, i) => (
                      <a className="ls-row" key={i} href={a.url} target="_blank" rel="noreferrer">
                        <div className="dp-glyph sm dir-event">◍</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="ls-row-top"><span className="mono muted small">{a.domain}</span></div>
                          <div className="ls-row-hl">{a.title}</div>
                        </div>
                      </a>
                    ))
                  ) : (
                    <div className="muted small" style={{ padding: 14 }}>
                      News feed off — GDELT headlines attach when connected, never fabricated.
                    </div>
                  )
                ) : shown.length === 0 ? (
                  <Empty icon="◍" title="No signals in this filter" />
                ) : (
                  shown.map((s) => {
                    const on = selected?.id === s.id;
                    return (
                      <button key={s.id} className={`ls-row${on ? " active" : ""}`} onClick={() => setSelId(s.id)}>
                        <div className={`dp-glyph sm dir-${s.dir}`}>{GLYPH[s.dir]}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="ls-row-top">
                            <span className="mono muted small">{s.country ?? "global"}</span>
                            <span className="ls-row-kind">{DIR_LABEL[s.dir]}</span>
                          </div>
                          <div className="ls-row-hl">{s.company} · {s.label}</div>
                        </div>
                        <span className="mono muted small ls-row-co">{s.slug.toUpperCase()}</span>
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            {/* MAP */}
            <section className="ls-map">
              <SignalsGlobe signals={located} selectedId={selected?.id ?? null} onSelect={setSelId} />
              <div className="ls-map-hint mono">globe eases to your selection · click a signal</div>
              <div className="ls-legend">
                <div><span className="ls-leg-dot" style={{ background: "var(--danger)" }} /> risk</div>
                <div><span className="ls-leg-dot" style={{ background: "var(--good)" }} /> opportunity</div>
                <div><span className="ls-leg-dot" style={{ background: "var(--accent)" }} /> signal</div>
              </div>
              {selected ? (
                <div className="ls-detail">
                  <div className={`dp-glyph dir-${selected.dir}`}>{GLYPH[selected.dir]}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="ls-detail-meta">
                      <span className={`ls-detail-cat dir-${selected.dir}`}>{DIR_LABEL[selected.dir]}</span>
                      <span className="mono muted small">{selected.country ?? "global"}</span>
                      {selected.source ? (
                        <a className="src-link" href={selected.source} target="_blank" rel="noreferrer">
                          <span className="arrow">↳</span> {selected.section || "source"}
                        </a>
                      ) : null}
                    </div>
                    <div className="ls-detail-hl">{selected.company} · {selected.label}</div>
                    <div className="ls-detail-why">{selected.why}</div>
                  </div>
                  <div className="ls-detail-actions">
                    <Link className="btn" to="/changes">Open insight →</Link>
                    <Link className="btn ghost" to="/atlas">Open in Atlas ✦</Link>
                  </div>
                </div>
              ) : null}
            </section>
          </div>

          {data && data.sigs.length > 0 && (
            <div className="changes-ticker" style={{ marginTop: 14 }}>
              <div className="changes-ticker-tag"><span className="dot" /> Live feed</div>
              <div className="changes-ticker-view">
                <div className="changes-ticker-track">
                  {[0, 1].map((dup) =>
                    data.sigs.slice(0, 18).map((s, i) => (
                      <span className="changes-ticker-item" key={`${dup}-${i}`}>
                        <span className={`changes-ticker-dot dir-${s.dir}`} />
                        <span>{s.company} · {s.label}</span>
                        <span className="mono muted small">{s.country ?? "global"}</span>
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
