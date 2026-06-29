import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { api, tokenStore } from "./api";

interface AuthState {
  email: string | null;
  ready: boolean; // initial token validation finished
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((user) => setEmail(user.email))
      .catch(() => {
        tokenStore.clear();
      })
      .finally(() => setReady(true));
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      email,
      ready,
      login: async (e, p) => {
        const res = await api.login(e, p);
        tokenStore.set(res.token);
        setEmail(res.email);
      },
      register: async (e, p) => {
        const res = await api.register(e, p);
        tokenStore.set(res.token);
        setEmail(res.email);
      },
      logout: () => {
        tokenStore.clear();
        setEmail(null);
      },
    }),
    [email, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
