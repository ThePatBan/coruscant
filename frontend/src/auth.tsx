import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { api, tokenStore } from "./api";

interface AuthState {
  email: string | null;
  // Account role from /auth/me (e.g. "admin"). Null until the session resolves, or
  // for the brief window after login before the profile refetch completes.
  role: string | null;
  ready: boolean; // initial token validation finished
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((user) => {
        setEmail(user.email);
        setRole(user.role);
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
      ready,
      login: async (e, p) => {
        const res = await api.login(e, p);
        tokenStore.set(res.token);
        setEmail(res.email);
        // Backfill the role; the login response only carries the token + email.
        void api.me().then((u) => setRole(u.role)).catch(() => setRole(null));
      },
      register: async (e, p) => {
        const res = await api.register(e, p);
        tokenStore.set(res.token);
        setEmail(res.email);
        void api.me().then((u) => setRole(u.role)).catch(() => setRole(null));
      },
      logout: () => {
        tokenStore.clear();
        setEmail(null);
        setRole(null);
      },
    }),
    [email, role, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
