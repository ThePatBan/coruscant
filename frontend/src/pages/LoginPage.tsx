import { type FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";

export function LoginPage() {
  const { email: current, login, register } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/atlas";
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("demo@coruscant.local");
  const [password, setPassword] = useState("coruscant-demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (current) return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      navigate(from);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <Link to="/" className="brand">
          <div className="logo" />
          <div className="name">Coruscant</div>
        </Link>
        <h2 style={{ textAlign: "center", marginTop: 14 }}>
          {mode === "login" ? "Sign in" : "Create your account"}
        </h2>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            autoComplete="email"
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
        </div>

        {error ? (
          <div className="errbox" style={{ marginTop: 14 }}>
            {error}
          </div>
        ) : null}

        <button className="btn" type="submit" disabled={busy}>
          {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <div className="auth-switch">
          {mode === "login" ? (
            <>
              No account?{" "}
              <button type="button" onClick={() => setMode("register")}>
                Create one
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button type="button" onClick={() => setMode("login")}>
                Sign in
              </button>
            </>
          )}
        </div>

        <div className="demo-hint">
          Demo account is pre-filled — just press <strong>Sign in</strong>.
        </div>
      </form>
    </div>
  );
}
