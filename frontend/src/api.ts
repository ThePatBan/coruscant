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

export interface DocumentDetail extends DocumentSummary {
  sections: Array<Record<string, unknown>>;
  entities: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
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

export interface AuthToken {
  token: string;
  email: string;
}

export interface CurrentUser {
  email: string;
  created_at: string | null;
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
  // auth
  login: (email: string, password: string) => post<AuthToken>("/auth/login", { email, password }),
  register: (email: string, password: string) =>
    post<AuthToken>("/auth/register", { email, password }),
  me: () => get<CurrentUser>("/auth/me"),
  resetRequest: (email: string) =>
    post<{ email: string; reset_token: string | null }>("/auth/reset/request", { email }),
};
