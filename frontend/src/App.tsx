import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./auth";
import { useAsync } from "./hooks";
import { AskPage } from "./pages/AskPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyDetailPage } from "./pages/CompanyDetailPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { GraphPage } from "./pages/GraphPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { SourcesPage } from "./pages/SourcesPage";
import { WatchlistsPage } from "./pages/WatchlistsPage";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "◧" },
  { to: "/search", label: "Search", icon: "⌕" },
  { to: "/companies", label: "Companies", icon: "▤" },
  { to: "/graph", label: "Entity graph", icon: "◬" },
  { to: "/watchlists", label: "Watchlists", icon: "🔔" },
  { to: "/documents", label: "Documents", icon: "▦" },
  { to: "/sources", label: "Sources", icon: "⌥" },
  { to: "/monitoring", label: "Monitoring", icon: "◉" },
];

const CRUMBS: Array<[RegExp, string]> = [
  [/^\/dashboard/, "Dashboard"],
  [/^\/search/, "Search the evidence"],
  [/^\/companies\/.+/, "Company"],
  [/^\/companies$/, "Companies"],
  [/^\/graph/, "Entity graph"],
  [/^\/watchlists/, "Watchlists"],
  [/^\/documents\/.+/, "Document"],
  [/^\/documents$/, "Documents"],
  [/^\/sources$/, "Sources"],
  [/^\/monitoring/, "Source monitoring"],
];

function HealthPills() {
  const { data, error } = useAsync(() => api.health(), []);
  if (error) {
    return (
      <span className="pill">
        <span className="dot warn" />
        API offline
      </span>
    );
  }
  if (!data) return <span className="pill"><span className="spinner" style={{ width: 12, height: 12 }} /></span>;
  return (
    <>
      <span className="pill">
        <span className="dot" />
        {data.documents} docs
      </span>
      <span className="pill">{data.graph_nodes} nodes</span>
    </>
  );
}

function ProtectedLayout() {
  const { email, ready, logout } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
        <span className="spinner" style={{ width: 26, height: 26 }} />
      </div>
    );
  }
  if (!email) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  const crumb = CRUMBS.find(([re]) => re.test(location.pathname))?.[1] ?? "";

  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/dashboard" className="brand">
          <div className="logo" />
          <div>
            <div className="name">Coruscant</div>
            <div className="tag">Intelligence</div>
          </div>
        </NavLink>

        <nav className="nav">
          <div className="label">Workspace</div>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to}>
              <span className="ico">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="foot">
          Evidence-based intelligence. Every insight traces back to its source.
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="crumb">{crumb}</div>
          <div className="stats">
            <HealthPills />
            <span className="pill accent" title={email}>
              {email}
            </span>
            <button className="btn ghost" onClick={logout} style={{ padding: "6px 12px" }}>
              Sign out
            </button>
          </div>
        </header>
        <div className="content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedLayout />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/search" element={<AskPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/companies/:slug" element={<CompanyDetailPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/watchlists" element={<WatchlistsPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:id" element={<DocumentDetailPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
