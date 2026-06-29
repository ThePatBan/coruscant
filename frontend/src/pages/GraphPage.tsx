import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EntityProfile, type ExposureResult } from "../api";
import { Empty, Loading } from "../components";
import { useAsync } from "../hooks";

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
          Which suppliers and companies are exposed to a country.
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
              <div className="change-row" key={i}>
                <span className="change-mark" style={{ color: "var(--evidence)" }}>⚠</span>
                <div>
                  <Link to={`/companies/${p.company.key}`} style={{ fontWeight: 560 }}>
                    {p.company.name}
                  </Link>{" "}
                  <span className="faint">exposed via</span>{" "}
                  <span className="pill">{p.via.name}</span>
                </div>
              </div>
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function CoExecutivesCard() {
  const { data } = useAsync(() => api.coExecutives(), []);
  return (
    <div className="card stack gap">
      <div>
        <h2>Connected executives</h2>
        <p className="faint" style={{ fontSize: 13 }}>
          People who bridge companies, and executives who shared a company.
        </p>
      </div>
      {!data ? (
        <Loading label="Loading" />
      ) : (
        <div className="stack gap-sm">
          {data.multi_company_people.map((b) => (
            <div className="wrap" key={b.person.key} style={{ gap: 8 }}>
              <span className="pill accent">{b.person.name}</span>
              <span className="faint">→</span>
              {b.companies.map((c) => (
                <span className="badge" key={c.key}>{c.name}</span>
              ))}
            </div>
          ))}
          {data.shared_company_groups
            .filter((g) => g.people.length >= 2)
            .map((g) => (
              <div className="wrap" key={g.company.key} style={{ gap: 8 }}>
                <span className="badge">{g.company.name}</span>
                <span className="faint">shared by</span>
                {g.people.map((p) => (
                  <span className="pill" key={p.key}>{p.name}</span>
                ))}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function EntityExplorer() {
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
          <div className="list" style={{ maxHeight: 420, overflow: "auto" }}>
            {list.data.map((e) => (
              <div className="li" key={`${e.kind}-${e.key}`} onClick={() => void open(e.kind, e.key)}>
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
          <div className="card stack gap-sm">
            <div className="wrap">
              <h2>{selected.entity.name}</h2>
              <span className="badge">{selected.entity.kind}</span>
            </div>
            {selected.relationships.length === 0 ? (
              <span className="faint">No relationships.</span>
            ) : (
              selected.relationships.map((r, i) => (
                <div className="wrap" key={i} style={{ gap: 8 }}>
                  <span className="cat" data-c={r.relation}>{r.relation.replace(/_/g, " ")}</span>
                  <span className="faint">{r.direction === "out" ? "→" : "←"}</span>
                  <span className="badge">{r.other.kind}</span>
                  <span>{r.other.name}</span>
                </div>
              ))
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
          <Empty icon="◬" title="Select an entity" hint="Click any entity to see its relationships." />
        )}
      </div>
    </div>
  );
}

export function GraphPage() {
  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Entity graph</h1>
        <p className="sub">
          Companies, people, suppliers, countries, products, and technologies — connected. Ask
          cross-entity questions that isolated documents cannot answer.
        </p>
      </div>
      <div className="grid cols-2">
        <ExposureCard />
        <CoExecutivesCard />
      </div>
      <h2>Entity explorer</h2>
      <EntityExplorer />
    </div>
  );
}
