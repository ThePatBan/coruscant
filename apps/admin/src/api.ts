// Typed client for the Coruscant *internal admin* API. This is a focused subset of
// the platform client — only the transport, the auth handshake, and the admin
// surfaces (model routing + customers). It deliberately does NOT pull in the
// customer-facing console's endpoints; the admin app is a separate deployable that
// talks to its own same-origin `/api` (nginx proxies to the API on admin.coruscant.com).

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

// ---- transport -------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    // A 401 *while holding a token* means the admin session expired or was revoked:
    // clear it and reload so the auth gate falls back to the sign-in screen. A 401 on
    // the login call itself is a bad-credentials error and must NOT trigger the reset.
    if (res.status === 401 && tokenStore.get() && !path.startsWith("/auth/login")) {
      tokenStore.clear();
      if (typeof window !== "undefined") window.location.reload();
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

// ---- auth ------------------------------------------------------------------

export interface AuthToken {
  token: string;
  email: string;
}

export interface CurrentUser {
  email: string;
  created_at: string | null;
  role: string;
}

// ---- admin console (model routing + customers) -----------------------------

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

export const api = {
  // auth
  login: (email: string, password: string) => post<AuthToken>("/auth/login", { email, password }),
  me: () => get<CurrentUser>("/auth/me"),

  // admin console
  adminLLM: () => get<LLMConfig>("/admin/llm"),
  adminLLMSave: (config: LLMConfigIn) => put<LLMConfig>("/admin/llm", config),
  adminLLMTest: (tier: string) => post<LLMTestResult>(`/admin/llm/test/${tier}`, {}),
  adminCustomers: () => get<Customer[]>("/admin/customers"),
};
