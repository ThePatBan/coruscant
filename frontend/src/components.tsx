import type { ReactNode } from "react";

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
