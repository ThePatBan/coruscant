// The progress history — a company's life rendered as a git log, not a feed.
//
// Two kinds of commit are merged into one dated stream: a *material change*
// (a ChangeSet: what was added/removed versus the prior disclosure, with the
// evidence behind each line) and an *event* (an extracted, categorized
// occurrence). Both carry the source so every line stays traceable.

import { useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ChangeSet, TimelineEvent } from "./api";
import { Cat, Empty } from "./components";

const RISK_CATEGORIES = new Set(["risk", "regulatory", "litigation", "supply_chain"]);
const OPPORTUNITY_CATEGORIES = new Set(["opportunity", "product", "capital_allocation"]);

export interface DiffLine {
  kind: "added" | "removed";
  category: string;
  statement: string;
  evidence?: { canonicalId: string | null; sectionTitle: string | null; sourceUri: string };
}

export interface Commit {
  id: string;
  hash: string;
  companySlug: string;
  companyName: string;
  category: string;
  title: string;
  when: string | null;
  material: boolean;
  canonicalId: string | null;
  sourceUri?: string;
  sectionTitle?: string | null;
  diff?: DiffLine[];
  description?: string;
}

const shortHash = (id: string | null | undefined): string =>
  id ? id.replace(/[^a-z0-9]/gi, "").slice(-7) || "0000000" : "0000000";

function changeCommit(cs: ChangeSet, companyName: string, when: string | null): Commit {
  const cat = cs.changes[0]?.category ?? "disclosure";
  return {
    id: `chg-${cs.current_canonical_id}`,
    hash: shortHash(cs.current_canonical_id),
    companySlug: cs.company_slug,
    companyName,
    category: cat,
    title: cs.current_title
      ? `Revised: ${cs.current_title}`
      : `${cs.added_count} added · ${cs.removed_count} removed vs prior disclosure`,
    when,
    material: true,
    canonicalId: cs.current_canonical_id,
    diff: cs.changes.map((c) => ({
      kind: c.kind,
      category: c.category,
      statement: c.statement,
      evidence: {
        canonicalId: c.evidence.canonical_id,
        sectionTitle: c.evidence.section_title,
        sourceUri: c.evidence.source_uri,
      },
    })),
  };
}

function eventCommit(e: TimelineEvent, companyName: string): Commit {
  return {
    id: `evt-${e.canonical_id}-${e.title}`,
    hash: shortHash(e.canonical_id),
    companySlug: e.company_slug,
    companyName,
    category: e.category,
    title: e.title,
    when: e.occurred_at,
    material: false,
    canonicalId: e.canonical_id,
    sourceUri: e.source_uri,
    sectionTitle: e.section_title,
    description: e.description,
  };
}

/**
 * Merge per-company change-sets and events into one descending-date commit log.
 * `dateFor` resolves a canonical id to a publication date so change commits that
 * carry no timestamp of their own still land in the right place on the rail.
 */
export function buildCommits(
  changeSets: ChangeSet[],
  events: TimelineEvent[],
  nameFor: (slug: string) => string,
  dateFor: (canonicalId: string | null) => string | null,
): Commit[] {
  const commits: Commit[] = [];
  for (const cs of changeSets) {
    if (!cs.material) continue;
    commits.push(changeCommit(cs, nameFor(cs.company_slug), dateFor(cs.current_canonical_id)));
  }
  for (const e of events) {
    commits.push(eventCommit(e, nameFor(e.company_slug)));
  }
  // Most-recent first; undated commits sink to the bottom rather than floating up.
  return commits.sort((a, b) => {
    if (a.when && b.when) return b.when.localeCompare(a.when);
    if (a.when) return -1;
    if (b.when) return 1;
    return 0;
  });
}

type Filter = "all" | "material" | "risk" | "opportunity";

function matches(commit: Commit, filter: Filter): boolean {
  switch (filter) {
    case "material":
      return commit.material;
    case "risk":
      return RISK_CATEGORIES.has(commit.category);
    case "opportunity":
      return OPPORTUNITY_CATEGORIES.has(commit.category);
    default:
      return true;
  }
}

export function ProgressLog({ commits, limit = 24 }: { commits: Commit[]; limit?: number }) {
  const [filter, setFilter] = useState<Filter>("all");
  const panelId = useId();

  const counts = useMemo(
    () => ({
      all: commits.length,
      material: commits.filter((c) => c.material).length,
      risk: commits.filter((c) => RISK_CATEGORIES.has(c.category)).length,
      opportunity: commits.filter((c) => OPPORTUNITY_CATEGORIES.has(c.category)).length,
    }),
    [commits],
  );

  const shown = commits.filter((c) => matches(c, filter)).slice(0, limit);
  const tabs: Array<[Filter, string]> = [
    ["all", "All"],
    ["material", "Material"],
    ["risk", "Risk"],
    ["opportunity", "Opportunity"],
  ];

  return (
    <div className="stack gap">
      <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
        <div className="segmented" role="tablist" aria-label="Filter progress history">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={filter === key}
              aria-controls={panelId}
              className={filter === key ? "active" : ""}
              onClick={() => setFilter(key)}
            >
              {label}
              <span className="ct">{counts[key]}</span>
            </button>
          ))}
        </div>
        <span className="faint" style={{ fontSize: 12 }}>
          {shown.length} of {counts[filter]} commits
        </span>
      </div>

      <div id={panelId}>
        {shown.length === 0 ? (
          <Empty icon="⎇" title="No history in this view" hint="Switch filters to see other commits." />
        ) : (
          <div className="commits">
            {shown.map((c) => (
              <CommitRow commit={c} key={c.id} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function CommitRow({ commit }: { commit: Commit }) {
  const target = commit.canonicalId ? `/documents/${commit.canonicalId}` : null;
  return (
    <article className={`commit${commit.material ? " material" : ""}`}>
      <div className="commit-rail" aria-hidden="true">
        <span className="commit-dot" />
      </div>
      <div className="commit-body">
        <div className="commit-head">
          <Link to={`/companies/${commit.companySlug}`} className="commit-co">
            {commit.companyName}
          </Link>
          <Cat category={commit.category} />
          {commit.material ? <span className="material-badge">material</span> : null}
          <span className="commit-when">{commit.when ?? "undated"}</span>
          <span className="commit-hash">{commit.hash}</span>
        </div>
        <div className="commit-title">{commit.title}</div>

        {commit.diff && commit.diff.length > 0 ? (
          <div className="commit-diff">
            {commit.diff.map((d, i) => (
              <div className={`diffline ${d.kind}`} key={i}>
                <span className="mk">{d.kind === "added" ? "+" : "−"}</span>
                <span className="grow">
                  {d.statement}
                  {d.evidence?.canonicalId ? (
                    <Link
                      to={`/documents/${d.evidence.canonicalId}`}
                      className="diff-src"
                      title={d.evidence.sourceUri}
                    >
                      ↳ {d.evidence.sectionTitle ?? "source"}
                    </Link>
                  ) : (
                    <span className="diff-src" title="No source document on this line">
                      ⚠ unverified
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        ) : commit.description ? (
          <div className="faint" style={{ fontSize: 13, marginTop: 4 }}>
            {commit.description}
          </div>
        ) : null}

        {target ? (
          <Link to={target} className="commit-src" title={commit.sourceUri ?? undefined}>
            ↳ {commit.sectionTitle ?? "source disclosure"}
          </Link>
        ) : null}
      </div>
    </article>
  );
}
