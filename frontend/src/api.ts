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

// Broadcast that the user's notification state changed (a watchlist was
// re-checked, or alerts were marked read) so any mounted unread-badge can
// refresh without a shared store or polling timer.
export const NOTIFICATIONS_EVENT = "coruscant:notifications";
export function emitNotificationsChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(NOTIFICATIONS_EVENT));
}

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
  // Human-readable edge fact: officer role (employs) / subsidiary jurisdiction.
  detail?: string | null;
}

// Event -> portfolio exposure. Direct = a legal entity in the jurisdiction
// (Exhibit-21, evidence-backed). Network = peers whose filings name a directly-
// exposed company (an orientation hint, not dollar magnitude).
export interface JurisdictionFootprint {
  company: EntityRef;
  subsidiaries: string[];
  source?: string | null;
}
export interface NetworkProximity {
  company: EntityRef;
  names: EntityRef;
  entity_name?: string | null;
  source?: string | null;
}
export interface JurisdictionExposure {
  jurisdiction: string;
  direct: JurisdictionFootprint[];
  network: NetworkProximity[];
}

// Thematic (GICS) exposure. `sector_exposure` matches at any hierarchy level — a
// sector (Information Technology) or a sub-industry (Semiconductors).
export interface SectorCount {
  sector: string;
  companies: number;
}
export interface SectorExposure {
  sector: string;
  matched_level?: string | null;
  direct: EntityRef[];
  network: NetworkProximity[];
}
export interface GicsSubIndustry {
  sub_industry: string;
  industry: string;
  code?: string | null;
  companies: EntityRef[];
}
export interface GicsSector {
  sector: string;
  companies: number;
  sub_industries: GicsSubIndustry[];
}

// MSCI market-tier (DM/EM/FM) composition — pathway 4.
export interface MarketTierCount {
  tier: string;
  label: string;
  companies: number;
}
export interface MarketTierExposure {
  tier: string;
  label: string;
  direct: EntityRef[];
}

// Live "since yesterday" quotes (Yahoo Finance, free). `connected` is false when
// the feed is off — the UI shows the stub then, never a fabricated number.
export interface HoldingQuote {
  slug: string;
  name: string;
  symbol: string;
  price: number;
  change_pct: number;
  currency?: string | null;
}
export interface PortfolioPrices {
  connected: boolean;
  as_of?: string | null;
  priced: number;
  total: number;
  avg_change_pct?: number | null;
  gainers: number;
  losers: number;
  holdings: HoldingQuote[];
  note?: string | null;
}

// Non-equity instruments (commodities, debt) and their exposure into equities.
export interface CommodityRef {
  slug: string;
  name: string;
  category: string;
  symbol?: string | null;
  affects_sectors: string[];
}
export interface DebtRef {
  slug: string;
  name: string;
  debt_type: string;
  issuer_country: string;
  symbol?: string | null;
}
export interface CommodityExposure {
  slug: string;
  commodity: string;
  category: string;
  affects_sectors: string[];
  holdings: EntityRef[];
}

// Sector-index benchmarking: each GICS sector's holdings vs a sector-ETF proxy.
export interface SectorBenchmark {
  sector: string;
  holdings: number;
  weight_pct: number;
  portfolio_change_pct?: number | null;
  benchmark_symbol?: string | null;
  benchmark_name?: string | null;
  benchmark_change_pct?: number | null;
  delta_pct?: number | null;
}
export interface PortfolioBenchmark {
  connected: boolean;
  as_of?: string | null;
  sectors: SectorBenchmark[];
  note?: string | null;
}

// Country macro (World Bank GDP/inflation + benchmark-index move).
export interface MacroMetric {
  label: string;
  value?: number | null;
  unit: string;
  period?: string | null;
  source: string;
}
export interface IndexQuote {
  name: string;
  symbol: string;
  price: number;
  change_pct: number;
  as_of?: string | null;
}
export interface CountryMacro {
  country: string;
  connected: boolean;
  metrics: MacroMetric[];
  index?: IndexQuote | null;
  note?: string | null;
}

// Business-news headlines (free GDELT). `connected` false ⇒ show the stub.
export interface Article {
  title: string;
  url: string;
  domain?: string | null;
  published_at?: string | null;
  source_country?: string | null;
  language?: string | null;
  image?: string | null;
}
export interface NewsFeed {
  connected: boolean;
  scope: string;
  country?: string | null;
  articles: Article[];
  note?: string | null;
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

export interface NotificationSummary {
  total: number;
  unread: number;
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
  generator: string; // "llm:<model>" when reasoned by a model, else "reference-analyst"
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

export interface ResolvedPosition {
  input_ticker?: string | null;
  input_name?: string | null;
  input_isin?: string | null;
  input_sedol?: string | null;
  company_key?: string | null;
  method: "ticker" | "isin" | "sedol" | "name" | "unresolved";
  score?: number | null;
}

export interface ResolveReport {
  total: number;
  resolved: number;
  by_ticker: number;
  by_isin: number;
  by_sedol: number;
  by_name: number;
  unresolved: number;
  positions: ResolvedPosition[];
}

export interface PortfolioUploadResult {
  portfolio: Portfolio;
  report: ResolveReport;
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
    // A 401 *while holding a token* means the session expired or was revoked: clear
    // it and send the user back to login. An ANONYMOUS 401 (no token — a public
    // visitor hitting an authenticated-only extra) must NOT force login; the page
    // degrades gracefully instead, so public browsing is never yanked to sign-in.
    if (
      res.status === 401 &&
      tokenStore.get() &&
      !path.startsWith("/auth/login") &&
      !path.startsWith("/auth/register")
    ) {
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
const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });

// ---- Admin console (model routing + customers) -----------------------------
export interface LLMProvider {
  kind: string;
  base_url: string;
  label: string;
  has_key: boolean;
}
export interface LLMRoute {
  provider: string;
  model: string;
}
export interface LLMConfig {
  tiers: string[];
  tier_hints: Record<string, string>;
  providers: Record<string, LLMProvider>;
  routes: Record<string, LLMRoute>;
  available: Record<string, boolean>;
}
// On save, omit api_key to keep the stored one; send "" to clear, or a new value.
export interface LLMProviderIn {
  kind: string;
  base_url: string;
  label: string;
  api_key?: string | null;
}
export interface LLMConfigIn {
  providers: Record<string, LLMProviderIn>;
  routes: Record<string, LLMRoute>;
}
export interface LLMTestResult {
  ok: boolean;
  tier: string;
  model?: string | null;
  provider?: string;
  latency_ms?: number;
  sample?: string;
  error?: string;
}
export interface Customer {
  email: string;
  role: string;
  created_at: string;
  api_calls: number;
}

export interface ScreeningHit {
  person: EntityRef;
  listing: EntityRef;
  relation: string;
  review_status: string;
  score: number | null;
  matched_name: string | null;
  dataset: string | null;
  source: string | null;
  source_url: string | null;
  valid_from: string | null;
  access_tier: string;
}

export interface ScreeningOverview {
  connected: boolean;
  provider: string | null;
  dataset: string | null;
  screened: number;
  candidates: number;
  pep: number;
  sanctioned: number;
  confirmed: ScreeningHit[];
  needs_review: ScreeningHit[];
  note: string;
}

// Ownership substrate — the three DISTINCT edge types (declared ownership ≠
// beneficial ownership ≠ accounting consolidation), never conflated, plus the UBO
// chains and group/UBO contagion built on top. Access-tier aware: restricted edges
// are counted, not shown.
export interface OwnershipOverview {
  connected: boolean;
  owns: number;
  beneficial_owner_of: number;
  consolidates: number;
  restricted: number;
  subjects_unresolved: number;
  holders_unresolved: number;
  provider: string | null;
  observed_at: string | null;
  market: string | null;
  note: string;
}

export interface OwnerEdge {
  holder_kind: string;
  holder_key: string;
  holder_name: string | null;
  relation: string; // owns | beneficial_owner_of | consolidates
  basis: string | null;
  percentage: number | null;
  percentage_band: string | null;
  interest: string | null;
  source: string | null;
  source_url: string | null;
  access_tier: string | null;
  valid_from: string | null;
  valid_to: string | null;
  holder_resolved: boolean | null;
}

export interface CompanyOwners {
  company_key: string;
  connected: boolean;
  owners: OwnerEdge[];
  restricted: number;
  provider: string | null;
  observed_at: string | null;
  market: string | null;
}

export interface ChainLink {
  holder: EntityRef;
  subject: EntityRef;
  relation: string;
  basis: string | null;
  percentage: number | null;
  percentage_band: string | null;
  interest: string | null;
  source: string | null;
  source_url: string | null;
  valid_from: string | null;
  valid_to: string | null;
  holder_resolved: boolean | null;
  access_tier: string | null;
}

export interface OwnershipChain {
  links: ChainLink[];
  // beneficial_owner | root | unresolved | cycle | max_depth | restricted
  terminal: string;
  terminal_holder: EntityRef | null;
  depth: number;
  complete: boolean;
}

export interface CompanyOwnershipChains {
  company: EntityRef;
  chains: OwnershipChain[];
  resolved_chains: number;
  partial_chains: number;
  cyclic_chains: number;
  restricted: number;
  note: string;
}

export interface ContagionHop {
  from_entity: EntityRef;
  to_entity: EntityRef;
  relation: string;
  direction: string; // "up" | "down"
  basis: string | null;
  source: string | null;
  source_url: string | null;
  access_tier: string | null;
}

export interface ContagionMember {
  company: EntityRef;
  hops: number;
  link: string; // parent | subsidiary | shares-owner | group
  shared_owner: EntityRef | null;
  path: ContagionHop[];
}

export interface GroupContagion {
  seed: EntityRef;
  direct: EntityRef[];
  inherited: ContagionMember[];
  restricted: number;
  note: string;
}

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
  jurisdictionExposure: (jurisdiction: string) =>
    get<JurisdictionExposure>(`/graph/jurisdiction-exposure?jurisdiction=${encodeURIComponent(jurisdiction)}`),
  sectors: () => get<SectorCount[]>("/graph/sectors"),
  sectorExposure: (sector: string) =>
    get<SectorExposure>(`/graph/sector-exposure?sector=${encodeURIComponent(sector)}`),
  gicsBreakdown: () => get<GicsSector[]>("/graph/gics-breakdown"),
  marketTiers: () => get<MarketTierCount[]>("/graph/market-tiers"),
  marketTierExposure: (tier: string) =>
    get<MarketTierExposure>(`/graph/market-tier-exposure?tier=${encodeURIComponent(tier)}`),
  portfolioPrices: () => get<PortfolioPrices>("/portfolio/prices"),
  portfolioBenchmark: () => get<PortfolioBenchmark>("/portfolio/benchmark"),
  macro: (country: string) => get<CountryMacro>(`/macro?country=${encodeURIComponent(country)}`),
  news: (country?: string) =>
    get<NewsFeed>(`/news${country ? `?country=${encodeURIComponent(country)}` : ""}`),
  commodities: () => get<CommodityRef[]>("/instruments/commodities"),
  commodityExposure: (commodity: string) =>
    get<CommodityExposure>(`/graph/commodity-exposure?commodity=${encodeURIComponent(commodity)}`),
  countryDebt: (country: string) =>
    get<DebtRef[]>(`/graph/country-debt?country=${encodeURIComponent(country)}`),
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
  screening: () => get<ScreeningOverview>("/graph/screening"),
  // ownership substrate
  ownershipOverview: () => get<OwnershipOverview>("/graph/ownership"),
  companyOwners: (key: string) =>
    get<CompanyOwners>(`/graph/company/${encodeURIComponent(key)}/owners`),
  ownershipChain: (key: string) =>
    get<CompanyOwnershipChains>(`/graph/company/${encodeURIComponent(key)}/ownership-chain`),
  contagion: (key: string) =>
    get<GroupContagion>(`/graph/company/${encodeURIComponent(key)}/contagion`),
  // watchlists
  watchlists: () => get<Watchlist[]>("/watchlists"),
  createWatchlist: (name: string, items: WatchItem[]) =>
    post<{ watchlist: Watchlist; notifications_created: number }>("/watchlists", { name, items }),
  deleteWatchlist: (id: string) =>
    request<{ ok: boolean }>(`/watchlists/${encodeURIComponent(id)}`, { method: "DELETE" }),
  evaluateWatchlist: (id: string) =>
    post<{ notifications_created: number }>(`/watchlists/${encodeURIComponent(id)}/evaluate`, {}),
  evaluateAllWatchlists: () =>
    post<{ watchlists_evaluated: number; notifications_created: number }>("/watchlists/evaluate-all", {}),
  notifications: (unreadOnly = false) =>
    get<Notification[]>(`/notifications${unreadOnly ? "?unread_only=true" : ""}`),
  notificationsSummary: () => get<NotificationSummary>("/notifications/summary"),
  markRead: (id: string) =>
    post<{ ok: boolean }>(`/notifications/${encodeURIComponent(id)}/read`, {}),
  markAllRead: () => post<{ marked: number }>("/notifications/read-all", {}),
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
  resolveHoldings: (csv: string) => post<ResolveReport>("/portfolios/resolve", { csv }),
  uploadPortfolio: (name: string, csv: string) =>
    post<PortfolioUploadResult>("/portfolios/upload", { name, csv }),
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

  // admin console
  adminLLM: () => get<LLMConfig>("/admin/llm"),
  adminLLMSave: (config: LLMConfigIn) => put<LLMConfig>("/admin/llm", config),
  adminLLMTest: (tier: string) => post<LLMTestResult>(`/admin/llm/test/${tier}`, {}),
  adminCustomers: () => get<Customer[]>("/admin/customers"),
};
