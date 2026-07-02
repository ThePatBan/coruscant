import { Link } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorView, Loading } from "../components";
import { useAsync } from "../hooks";

export function CompaniesPage() {
  const { data, error, loading } = useAsync(() => api.companies(), []);

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Companies</h1>
        <p className="sub">
          The tracked universe. Open a company to see its documents and how it connects in the
          knowledge graph.
        </p>
      </div>

      {loading ? <Loading label="Loading companies" /> : null}
      {error ? <ErrorView error={error} /> : null}
      {data && data.length === 0 ? <Empty title="No companies configured" /> : null}

      {data && data.length > 0 ? (
        <div className="grid cols-3">
          {data.map((c) => (
            <Link to={`/companies/${c.slug}`} key={c.slug} className="card hover">
              <div className="stack gap-sm">
                <div className="row-between">
                  <h2>{c.name}</h2>
                  <span className="faint" style={{ fontSize: 18 }}>
                    →
                  </span>
                </div>
                <div className="wrap">
                  {c.industry ? <span className="pill accent">{c.industry}</span> : null}
                  {c.country ? <span className="pill">{c.country}</span> : null}
                </div>
                <div className="mono faint">{c.slug}</div>
              </div>
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
