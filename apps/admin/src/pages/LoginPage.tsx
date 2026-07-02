import { type FormEvent, useState } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";

// The internal admin sign-in. Same visual language as the console's login, but this is
// staff-only: after sign-in the App gate checks role === "admin" and shows a
// not-authorized notice to anyone else.
export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="brand">
          <div className="logo" />
          <div className="name">Coruscant</div>
        </div>
        <div className="pill" style={{ margin: "10px auto 0" }}>Internal admin</div>
        <h2 style={{ textAlign: "center", marginTop: 14 }}>Staff sign in</h2>

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
            autoComplete="current-password"
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
          {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Sign in"}
        </button>

        <div className="demo-hint">Coruscant operations only. Access is limited to admin accounts.</div>
      </form>
    </div>
  );
}
