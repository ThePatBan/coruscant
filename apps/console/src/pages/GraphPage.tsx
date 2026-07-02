import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EntityProfile, type ExposureResult } from "../api";
import { Empty, Loading, PanelHead, RelationGroups, Skeleton } from "../components";
import { graphStats, GraphIncompleteNote, RelationMap, useRelGraph } from "../graph";
import { useAsync } from "../hooks";
import { isEntityRelation } from "../relations";

const KINDS = ["Company", "Person", "Country", "Product", "Technology", "Agency"];

function ExposureCard() {
  const [country, setCountry] = useState("Taiwan");
  const [result, setResult] = useState<ExposureResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      setResult(await api.exposure(country));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack gap">
      <div>
        <h2>Supply-chain exposure</h2>
        <p className="faint" style={{ fontSize: 13 }}>
          Trace which companies are exposed to a country through the suppliers they depend on.
        </p>
      </div>
      <form onSubmit={run} className="wrap" style={{ gap: 8 }}>
        <input className="input" value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country" />
        <button className="btn" type="submit" disabled={busy}>
          {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Trace"}
        </button>
      </form>
      {result ? (
        result.direct.length === 0 ? (
          <Empty title={`No entities operate in ${result.country}`} />
        ) : (
          <div className="stack gap-sm">
            <div className="wrap">
              <span className="faint" style={{ fontSize: 12.5 }}>Operates in {result.country}:</span>
              {result.direct.map((d) => (
                <span className="pill accent" key={d.key}>{d.name}</span>
              ))}
            </div>
            {result.exposed.map((p, i) => (
              <div className="ctrl-row" key={i} style={{ padding: "9px 0" }}>
                <Link to={`/companies/${p.company.key}`} className="ctrl-actor tier-supply">
                  <span className="glyph">◧</span>
                  <span className="nm">{p.company.name}</span>
                </Link>
                <span className="ctrl-arrow">exposed via →</span>
                <span className="relchip tier-supply">{p.via.name}</span>
              </div>
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function CoExecutivesCard({ trackedKeys }: { trackedKeys?: Set<string> }) {
  const { data } = useAsync(() => api.coExecutives(), []);
  return (
    <div className="card stack gap">
      <div>
        <h2>Connected executives</h2>
        <p className="faint" style={{ fontSize: 13 }}>
          People who bridge companies, and the executives a company has shared.
        </p>
      </div>
      {!data ? (
        <Loading label="Loading" />
      ) : (
        <div className="stack gap-sm">
          {data.multi_company_people.map((b) => (
            <div className="ctrl-row" key={b.person.key} style={{ padding: "9px 0" }}>
              <span className="ctrl-actor tier-proxy">
                <span className="glyph">◍</span>
                <span className="nm">{b.person.name}</span>
              </span>
              <span className="ctrl-arrow">linked to →</span>
              <div className="ctrl-targets">
                {b.companies.map((c) =>
                  trackedKeys?.has(c.key) ? (
                    <Link className="relchip tier-proxy" to={`/companies/${c.key}`} key={c.key}>
                      {c.name}
                    </Link>
                  ) : (
                    <span className="relchip tier-proxy" key={c.key}>{c.name}</span>
                  ),
                )}
              </div>
            </div>
          ))}
          <div className="ctrl-note">
            <span className="inf">inferred</span>
            Links projected from the curated entity graph (current and prior roles). Open a company to
            review its source disclosures.
          </div>
        </div>
      )}
    </div>
  );
}

function EntityExplorer({ trackedKeys }: { trackedKeys?: Set<string> }) {
  const [kind, setKind] = useState("Company");
  const list = useAsync(() => api.entities(kind), [kind]);
  const [selected, setSelected] = useState<EntityProfile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);

  // Clear the stale profile when the entity kind changes.
  useEffect(() => setSelected(null), [kind]);

  async function open(k: string, key: string) {
    setLoadingProfile(true);
    try {
      setSelected(await api.entity(k, key));
    } finally {
      setLoadingProfile(false);
    }
  }

  return (
    <div className="grid cols-2">
      <div className="stack gap">
        <div className="wrap">
          {KINDS.map((k) => (
            <button
              key={k}
              className={`chip${k === kind ? " active" : ""}`}
              style={k === kind ? { borderColor: "var(--accent-border)", color: "var(--text)" } : undefined}
              onClick={() => setKind(k)}
            >
              {k}
            </button>
          ))}
        </div>
        {list.loading ? <Loading label="Loading entities" /> : null}
        {list.data ? (
          <div className="list" style={{ maxHeight: 460, overflow: "auto" }}>
            {list.data.map((e) => (
              <div
                className="li"
                key={`${e.kind}-${e.key}`}
                tabIndex={0}
                role="button"
                onClick={() => void open(e.kind, e.key)}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    void open(e.kind, e.key);
                  }
                }}
              >
                <div className="grow truncate" style={{ fontWeight: 530 }}>{e.name}</div>
                <span className="badge">{e.kind}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <div className="stack gap">
        {loadingProfile ? <Loading label="Loading entity" /> : null}
        {selected ? (
          <div className="card stack gap">
            <div className="wrap">
              <h2>{selected.entity.name}</h2>
              <span className="badge">{selected.entity.kind}</span>
            </div>
            {selected.relationships.filter((r) => isEntityRelation(r.relation)).length === 0 ? (
              <span className="faint">No relationships recorded.</span>
            ) : (
              <RelationGroups relationships={selected.relationships} trackedKeys={trackedKeys} />
            )}
            {selected.mentioned_in.length > 0 ? (
              <div className="faint" style={{ fontSize: 12.5 }}>
                Mentioned in{" "}
                {selected.mentioned_in.slice(0, 4).map((id, i) => (
                  <span key={id}>
                    {i > 0 ? ", " : ""}
                    <Link to={`/documents/${id}`} className="mono">doc</Link>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <Empty icon="◬" title="Select an entity" hint="Click any entity to see its relationships, grouped by tier." />
        )}
      </div>
    </div>
  );
}

export function GraphPage() {
  const { data, loading } = useRelGraph();
  const stats = data ? graphStats(data.graph) : null;

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Entity graph</h1>
        <p className="sub">
          Companies, people, suppliers, countries, products, and technologies — connected. Ask the
          cross-entity questions that isolated documents cannot answer.
        </p>
      </div>

      <section className="stack gap">
        <PanelHead
          idx="01"
          kicker="The connected universe"
          title="Every tracked entity, mapped"
          sub="Companies on the ring; their people, suppliers, products, and shared dependencies around them. Click a company to open it."
          right={
            stats ? (
              <div className="wrap" style={{ justifyContent: "flex-end" }}>
                <span className="pill">{stats.companies} companies</span>
                <span className="pill">{stats.links} edges</span>
              </div>
            ) : null
          }
        />
        {loading ? <Skeleton h={460} /> : data ? <RelationMap graph={data.graph} mode="full" /> : null}
        {data ? <GraphIncompleteNote failed={data.failed} /> : null}
      </section>

      <div className="grid cols-2">
        <ExposureCard />
        <CoExecutivesCard trackedKeys={data?.trackedKeys} />
      </div>

      <section className="stack gap">
        <PanelHead idx="02" kicker="Entity explorer" title="Inspect any entity" />
        <EntityExplorer trackedKeys={data?.trackedKeys} />
      </section>
    </div>
  );
}
