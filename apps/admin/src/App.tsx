import { canAccessAdmin } from "./access";
import { useAuth } from "./auth";
import { AdminConsolePage } from "./pages/AdminConsolePage";
import { LoginPage } from "./pages/LoginPage";

// The internal admin app shell. Three states, in order:
//   1. not ready        → a spinner while the stored session is validated
//   2. not an admin      → the sign-in screen (anonymous) or a not-authorized notice
//   3. admin              → the admin console under a minimal staff top bar
// The backend is the real gate (every /admin/* route is `require_admin`); this shell
// just avoids dead-ending non-admins and gives ops a clean, separate surface.
export default function App() {
  const { email, role, ready, logout } = useAuth();

  if (!ready) {
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
        <span className="spinner" style={{ width: 26, height: 26 }} />
      </div>
    );
  }

  // Anonymous → sign in. Signed-in-but-not-admin → an honest not-authorized notice.
  if (!email) return <LoginPage />;
  if (!canAccessAdmin(role)) return <NotAuthorized email={email} onLogout={logout} />;

  return (
    <div className="admin-app">
      <header className="admin-topbar">
        <div className="brand">
          <div className="logo" />
          <div className="brand-text">
            <div className="name">Coruscant</div>
            <div className="tag">Internal admin</div>
          </div>
        </div>
        <div className="stats">
          <span className="pill accent">{email}</span>
          <button className="btn ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="admin-main">
        <AdminConsolePage />
      </main>
    </div>
  );
}

function NotAuthorized({ email, onLogout }: { email: string; onLogout: () => void }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <div className="brand" style={{ justifyContent: "center" }}>
          <div className="logo" />
          <div className="name">Coruscant</div>
        </div>
        <div className="pill" style={{ margin: "10px auto 0" }}>Internal admin</div>
        <h2 style={{ marginTop: 14 }}>Not authorized</h2>
        <p className="faint" style={{ fontSize: 13 }}>
          You're signed in as <span className="mono">{email}</span>, which isn't an admin account.
          The internal admin console is limited to Coruscant operations staff.
        </p>
        <button className="btn ghost" style={{ marginTop: 8 }} onClick={onLogout}>
          Sign out
        </button>
      </div>
    </div>
  );
}
