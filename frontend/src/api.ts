// Typed client for the Coruscant API. All calls go to a same-origin `/api`
// prefix (Vite proxy in dev, nginx proxy in prod) and carry the bearer token
// when the user is authenticated.

const BASE = "/api";
const TOKEN_KEY = "coruscant.token";

export const tokenStore = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string): void => localStorage.setItem(TOKEN_KEY, token),
  clear: (): void => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// ---- types -----------------------------------------------------------------

export interface Health {
  status: string;
  documents: number;
  graph_nodes: number;
}

export interface Company {
  slug: string;
  name: string;
  industry: string | null;
  country: string | null;
}

export interface Source {
  source_type: string;
  label: string;
  document_type: string;
}

export interface DocumentSummary {
  canonical_id: string;
  title: string | null;
  document_type: string;
  source_uri: string;
  published_at: string | null;
}

export interface Provenance {
  source_type: string;
  source_uri: string;
  retrieved_at: string;
  authority: number;
  publisher: string | null;
  license: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  sections: Array<Record<string, unknown>>;
  entities: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  provenance: Provenance | null;
}

export interface EvidenceItem {
  source_uri: string;
  title: string | null;
  excerpt: string | null;
  section_title: string | null;
  canonical_id: string | null;
}

export interface RetrieveResult {
  title: string | null;
  source_uri: string;
  canonical_id: string;
  document_type: string | null;
  evidence: EvidenceItem[];
}

export interface RetrieveResponse {
  query: string;
  answer: string;
  results: RetrieveResult[];
}

export interface GraphNeighbor {
  relation: string;
  target_kind: string;
  target_key: string;
  title: string | null;
}

export interface GraphResponse {
  company_slug: string;
  found: boolean;
  neighbors: GraphNeighbor[];
}

export interface Claim {
  text: string;
  source_uri: string;
  section_title: string | null;
  canonical_id: string | null;
  category: string | null;
  confidence?: number;
}

export interface AISummary {
  canonical_id: string;
  company_slug: string;
  document_type: string;
  source_type: string;
  title: string | null;
  published_at: string | null;
  source_uri: string;
  overview: Claim;
  key_points: Claim[];
  risks: Claim[];
  opportunities: Claim[];
  management_commentary: Claim[];
  financial_highlights: Claim[];
  events: Claim[];
}

export interface TimelineEvent {
  canonical_id: string;
  company_slug: string;
  source_type: string;
  category: string;
  title: string;
  description: string;
  occurred_at: string | null;
  source_uri: string;
  section_title: string | null;
}

export interface DocumentChange {
  kind: "added" | "removed";
  category: string;
  statement: string;
  evidence: Claim;
  confidence: number;
}

export interface ChangeSet {
  company_slug: string;
  source_type: string;
  current_canonical_id: string;
  previous_canonical_id: string | null;
  current_title: string | null;
  previous_title: string | null;
  changes: DocumentChange[];
  material: boolean;
  added_count: number;
  removed_count: number;
}

export interface Dashboard {
  companies: number;
  documents: number;
  events: number;
  material_changes: number;
  latest_documents: DocumentSummary[];
  recent_events: TimelineEvent[];
  recent_risks: TimelineEvent[];
  recent_opportunities: TimelineEvent[];
}

export interface SourceReliability {
  source_type: string;
  label: string;
  authority: number;
  document_count: number;
  structure_score: number;
  completeness_score: number;
  success_rate: number;
  score: number;
  tier: string;
  latest_published: string | null;
}

export interface EntityRef {
  kind: string;
  key: string;
  name: string;
}

export interface Relationship {
  relation: string;
  direction: "out" | "in";
  other: EntityRef;
  // Provenance of the edge, e.g. "reference-entities" (curated graph) or
  // "document-mention". Returned by the backend; surfaced as a provenance hint.
  source?: string | null;
}

export interface EntityProfile {
  entity: EntityRef;
  properties: Record<string, unknown>;
  relationships: Relationship[];
  mentioned_in: string[];
}

export interface ExposurePath {
  company: EntityRef;
  via: EntityRef;
  relation: string;
}

export interface ExposureResult {
  country: string;
  direct: EntityRef[];
  exposed: ExposurePath[];
}

export interface CoExecutiveGroup {
  company: EntityRef;
  people: EntityRef[];
}

export interface BridgePerson {
  person: EntityRef;
  companies: EntityRef[];
}

export interface CoExecutiveResult {
  shared_company_groups: CoExecutiveGroup[];
  multi_company_people: BridgePerson[];
}

export interface WatchItem {
  type: string;
  value: string;
}

export interface Watchlist {
  id: string;
  name: string;
  items: WatchItem[];
  created_at: string;
}

export interface Notification {
  id: string;
  watchlist_id: string;
  watch_type: string;
  watch_value: string;
  kind: string;
  title: string;
  detail: string;
  category: string | null;
  source_uri: string | null;
  canonical_id: string | null;
  created_at: string;
  read: boolean;
}

export interface AnalysisStep {
  label: string;
  detail: string;
}

export interface AnalysisConcern {
  title: string;
  category: string;
  severity: string;
  confidence: number;
  rationale: string;
  evidence: Claim[];
}

export interface AnalysisReport {
  company_slug: string;
  company_name: string;
  question: string;
  focus: string;
  headline: string;
  steps: AnalysisStep[];
  concerns: AnalysisConcern[];
  disclaimer: string;
}

export interface Signal {
  type: string;
  company_slug: string;
  label: string;
  direction: string;
  strength: number;
  rationale: string;
  evidence: Claim[];
}

export interface Holding {
  company_slug: string;
  label?: string | null;
}

export interface Portfolio {
  id: string;
  name: string;
  holdings: Holding[];
  created_at: string;
}

export interface PortfolioBriefing {
  portfolio_id: string;
  name: string;
  holdings: Holding[];
  headline: string;
  material_changes: ChangeSet[];
  recent_events: TimelineEvent[];
  companies_with_changes: number;
}

export interface WorkspaceItem {
  id: string;
  type: string;
  title: string;
  body: string;
  ref: string | null;
  author_email: string;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  owner_email: string;
  members: string[];
  created_at: string;
  items: WorkspaceItem[];
}

export interface ApiKey {
  id: string;
  name: string;
  display: string;
  created_at: string;
}

export interface SavedSearch {
  id: string;
  name: string;
  query: string;
  source_type: string | null;
  created_at: string;
}

export interface AuthToken {
  token: string;
  email: string;
}

export interface CurrentUser {
  email: string;
  created_at: string | null;
  role: string;
}

// ---- transport -------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    // A 401 on anything other than the login/register attempt means the session
    // expired or was revoked: clear it and send the user back to login.
    if (res.status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/register")) {
      tokenStore.clear();
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  // data
  health: () => get<Health>("/health"),
  companies: () => get<Company[]>("/companies"),
  sources: () => get<Source[]>("/sources"),
  documents: (params: { company?: string; source_type?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.company) q.set("company", params.company);
    if (params.source_type) q.set("source_type", params.source_type);
    const qs = q.toString();
    return get<DocumentSummary[]>(`/documents${qs ? `?${qs}` : ""}`);
  },
  document: (id: string) => get<DocumentDetail>(`/documents/${encodeURIComponent(id)}`),
  companyGraph: (slug: string) => get<GraphResponse>(`/graph/company/${encodeURIComponent(slug)}`),
  retrieve: (query: string, topK = 6) => post<RetrieveResponse>("/retrieve", { query, top_k: topK }),
  // intelligence
  dashboard: () => get<Dashboard>("/dashboard"),
  documentSummary: (id: string) => get<AISummary>(`/documents/${encodeURIComponent(id)}/summary`),
  companyTimeline: (slug: string) =>
    get<TimelineEvent[]>(`/companies/${encodeURIComponent(slug)}/timeline`),
  companyChanges: (slug: string) =>
    get<ChangeSet[]>(`/companies/${encodeURIComponent(slug)}/changes`),
  // sources & graph
  monitoring: () => get<SourceReliability[]>("/monitoring"),
  entities: (kind?: string) =>
    get<EntityRef[]>(`/entities${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`),
  entity: (kind: string, key: string) =>
    get<EntityProfile>(`/entities/${encodeURIComponent(kind)}/${encodeURIComponent(key)}`),
  exposure: (country: string) =>
    get<ExposureResult>(`/graph/exposure?country=${encodeURIComponent(country)}`),
  coExecutives: () => get<CoExecutiveResult>("/graph/co-executives"),
  // watchlists
  watchlists: () => get<Watchlist[]>("/watchlists"),
  createWatchlist: (name: string, items: WatchItem[]) =>
    post<{ watchlist: Watchlist; notifications_created: number }>("/watchlists", { name, items }),
  deleteWatchlist: (id: string) =>
    request<{ ok: boolean }>(`/watchlists/${encodeURIComponent(id)}`, { method: "DELETE" }),
  evaluateWatchlist: (id: string) =>
    post<{ notifications_created: number }>(`/watchlists/${encodeURIComponent(id)}/evaluate`, {}),
  notifications: (unreadOnly = false) =>
    get<Notification[]>(`/notifications${unreadOnly ? "?unread_only=true" : ""}`),
  markRead: (id: string) =>
    post<{ ok: boolean }>(`/notifications/${encodeURIComponent(id)}/read`, {}),
  // saved searches & comparison
  savedSearches: () => get<SavedSearch[]>("/saved-searches"),
  createSavedSearch: (name: string, query: string, source_type?: string | null) =>
    post<SavedSearch>("/saved-searches", { name, query, source_type: source_type ?? null }),
  deleteSavedSearch: (id: string) =>
    request<{ ok: boolean }>(`/saved-searches/${encodeURIComponent(id)}`, { method: "DELETE" }),
  compare: (a: string, b: string) =>
    get<ChangeSet>(`/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  // analyst & signals
  analyst: (slug: string, question: string) =>
    post<AnalysisReport>(`/analyst/${encodeURIComponent(slug)}`, { question }),
  signals: (slug: string) => get<Signal[]>(`/signals/${encodeURIComponent(slug)}`),
  // portfolios
  portfolios: () => get<Portfolio[]>("/portfolios"),
  createPortfolio: (name: string, holdings: Holding[]) =>
    post<Portfolio>("/portfolios", { name, holdings }),
  deletePortfolio: (id: string) =>
    request<{ ok: boolean }>(`/portfolios/${encodeURIComponent(id)}`, { method: "DELETE" }),
  portfolioBriefing: (id: string) =>
    get<PortfolioBriefing>(`/portfolios/${encodeURIComponent(id)}/briefing`),
  // workspaces
  workspaces: () => get<Workspace[]>("/workspaces"),
  workspace: (id: string) => get<Workspace>(`/workspaces/${encodeURIComponent(id)}`),
  createWorkspace: (name: string, members: string[]) =>
    post<Workspace>("/workspaces", { name, members }),
  addWorkspaceItem: (id: string, item: { type: string; title: string; body?: string; ref?: string | null }) =>
    post<WorkspaceItem>(`/workspaces/${encodeURIComponent(id)}/items`, item),
  deleteWorkspaceItem: (id: string, itemId: string) =>
    request<{ ok: boolean }>(`/workspaces/${encodeURIComponent(id)}/items/${encodeURIComponent(itemId)}`, { method: "DELETE" }),
  deleteWorkspace: (id: string) =>
    request<{ ok: boolean }>(`/workspaces/${encodeURIComponent(id)}`, { method: "DELETE" }),
  // api keys
  apiKeys: () => get<ApiKey[]>("/api-keys"),
  createApiKey: (name: string) => post<{ key: ApiKey; secret: string }>("/api-keys", { name }),
  revokeApiKey: (id: string) =>
    request<{ ok: boolean }>(`/api-keys/${encodeURIComponent(id)}`, { method: "DELETE" }),
  // auth
  login: (email: string, password: string) => post<AuthToken>("/auth/login", { email, password }),
  register: (email: string, password: string) =>
    post<AuthToken>("/auth/register", { email, password }),
  me: () => get<CurrentUser>("/auth/me"),
  resetRequest: (email: string) =>
    post<{ email: string; reset_token: string | null }>("/auth/reset/request", { email }),
};
