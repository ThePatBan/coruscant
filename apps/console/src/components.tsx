import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Relationship } from "./api";
import { isEntityRelation, relationTier, relationVerb, TIERS, type RelationTier } from "./relations";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner" />
      {label}…
    </div>
  );
}

export function ErrorView({ error }: { error: string }) {
  return (
    <div className="errbox">
      <strong>Could not reach the API.</strong> {error}. Make sure the stack is running
      (<span className="mono">docker compose up</span>).
    </div>
  );
}

export function Empty({ icon = "∅", title, hint }: { icon?: string; title: string; hint?: ReactNode }) {
  return (
    <div className="empty">
      <div className="big">{icon}</div>
      <div style={{ color: "var(--text-muted)", fontWeight: 600 }}>{title}</div>
      {hint ? <div style={{ marginTop: 6 }}>{hint}</div> : null}
    </div>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  sec_edgar: "SEC EDGAR",
  investor_relations: "Investor Relations",
  earnings_call: "Earnings Call",
  press_release: "Press Release",
  job_postings: "Job Postings",
  news: "News",
  patents: "Patents",
};

const DOC_TYPE_LABELS: Record<string, string> = {
  filing: "Filing",
  investor_update: "Investor Update",
  transcript: "Transcript",
  press_release: "Press Release",
  job_posting: "Job Posting",
  news_article: "News",
  patent: "Patent",
};

export function sourceLabel(key: string): string {
  return SOURCE_LABELS[key] ?? key;
}

export function docTypeLabel(key: string): string {
  return DOC_TYPE_LABELS[key] ?? key.replace(/_/g, " ");
}

export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}

export function Cat({ category }: { category: string | null | undefined }) {
  const c = category ?? "general";
  return (
    <span className="cat" data-c={c}>
      {c.replace(/_/g, " ")}
    </span>
  );
}

/** Shimmer placeholder. Product surfaces load into skeletons, not spinners. */
export function Skeleton({ h = 16, w = "100%", style }: { h?: number | string; w?: number | string; style?: CSSProperties }) {
  return <div className="skel" style={{ height: h, width: w, ...style }} />;
}

/** Editorial panel header: numbered kicker, title, optional sub + right slot. */
export function PanelHead({
  idx,
  kicker,
  title,
  sub,
  right,
}: {
  idx?: string;
  kicker: string;
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <header className="panel-head">
      <div>
        <div className="kicker">
          {idx ? <span className="idx">{idx}</span> : null}
          {kicker}
        </div>
        <h2>{title}</h2>
        {sub ? <div className="sub">{sub}</div> : null}
      </div>
      {right ? <div>{right}</div> : null}
    </header>
  );
}

/** A relationship rendered in the shared visual-language: tier dot + verb + name. */
export function RelChip({
  relation,
  name,
  to,
}: {
  relation: string;
  name: string;
  to?: string;
}) {
  const tier = relationTier(relation);
  const body = (
    <>
      {relationVerb(relation)} <strong>{name}</strong>
    </>
  );
  if (to) {
    return (
      <Link className={`relchip tier-${tier}`} to={to}>
        {body}
      </Link>
    );
  }
  return <span className={`relchip tier-${tier}`}>{body}</span>;
}

/** Relationships grouped by analytical tier — the typed replacement for a flat list. */
export function RelationGroups({
  relationships,
  trackedKeys,
}: {
  relationships: Relationship[];
  trackedKeys?: Set<string>;
}) {
  const byTier = new Map<RelationTier, Relationship[]>();
  for (const r of relationships) {
    if (!isEntityRelation(r.relation)) continue;
    const tier = relationTier(r.relation);
    (byTier.get(tier) ?? byTier.set(tier, []).get(tier)!).push(r);
  }
  const order = TIERS.filter((t) => byTier.has(t.tier));
  if (order.length === 0) return null;
  return (
    <div>
      {order.map(({ tier, label }) => {
        const items = byTier.get(tier)!;
        return (
          <div className={`relgroup tier-${tier}`} key={tier}>
            <div className="relgroup-head">
              <span className="dot" />
              <h4>{label}</h4>
              <span className="ct">{items.length}</span>
            </div>
            <div className="relgrid">
              {items.map((r, i) => {
                const linkable = r.other.kind === "Company" && trackedKeys?.has(r.other.key);
                return (
                  <RelChip
                    key={`${r.relation}-${r.other.key}-${i}`}
                    relation={r.relation}
                    name={r.other.name}
                    to={linkable ? `/companies/${r.other.key}` : undefined}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
