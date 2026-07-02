import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { api, tokenStore } from "./api";

interface AuthState {
  email: string | null;
  // Account role from /auth/me (e.g. "admin"). Null until the session resolves, or
  // for the brief window after login before the profile refetch completes.
  role: string | null;
  // Whether the account holds the enterprise entitlement (backend /entitlements — the
  // single source of truth). The enterprise gate reads THIS, never role/plan directly.
  enterprise: boolean;
  ready: boolean; // initial token validation finished
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [enterprise, setEnterprise] = useState(false);
  const [ready, setReady] = useState(false);

  // Refresh the enterprise entitlement from the backend (never derived client-side).
  // A failure degrades to "not entitled" rather than clearing the session.
  const refreshEntitlements = () =>
    api
      .entitlements()
      .then((ent) => setEnterprise(ent.enterprise))
      .catch(() => setEnterprise(false));

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(async (user) => {
        setEmail(user.email);
        setRole(user.role);
        await refreshEntitlements();
      })
      .catch(() => {
        tokenStore.clear();
      })
      .finally(() => setReady(true));
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      email,
      role,
      enterprise,
      ready,
      login: async (e, p) => {
        const res = await api.login(e, p);
        tokenStore.set(res.token);
        setEmail(res.email);
        // Backfill role + entitlement; the login response only carries token + email.
        void api.me().then((u) => setRole(u.role)).catch(() => setRole(null));
        void refreshEntitlements();
      },
      register: async (e, p) => {
        const res = await api.register(e, p);
        tokenStore.set(res.token);
        setEmail(res.email);
        void api.me().then((u) => setRole(u.role)).catch(() => setRole(null));
        void refreshEntitlements();
      },
      logout: () => {
        tokenStore.clear();
        setEmail(null);
        setRole(null);
        setEnterprise(false);
      },
    }),
    [email, role, enterprise, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
