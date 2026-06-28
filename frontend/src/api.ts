// Typed client for the Coruscant API. All calls go to a same-origin `/api`
// prefix (Vite proxy in dev, nginx proxy in prod).

const BASE = "/api";

export interface Health {
  status: string;
  documents: number;
  graph_nodes: number;
  data_dir: string;
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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
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
  retrieve: async (query: string, topK = 5): Promise<RetrieveResponse> => {
    const res = await fetch(`${BASE}/retrieve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return (await res.json()) as RetrieveResponse;
  },
};
