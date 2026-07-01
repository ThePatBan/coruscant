import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, NOTIFICATIONS_EVENT } from "./api";
import { useAuth } from "./auth";
import { useAsync } from "./hooks";
import { AdminPage } from "./pages/AdminPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AtlasPage } from "./pages/AtlasPage";
import { AskPage } from "./pages/AskPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyDetailPage } from "./pages/CompanyDetailPage";
import { ComparePage } from "./pages/ComparePage";
import { CountryPage } from "./pages/CountryPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { GraphPage } from "./pages/GraphPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SourcesPage } from "./pages/SourcesPage";
import { WatchlistsPage } from "./pages/WatchlistsPage";
import { WorkspacesPage } from "./pages/WorkspacesPage";
import { WorldPage } from "./pages/WorldPage";

const NAV = [
  { to: "/world", label: "World", icon: "◍" },
  { to: "/country", label: "Country", icon: "⬡" },
  { to: "/atlas", label: "Company graph", icon: "✦" },
  { to: "/dashboard", label: "Dashboard", icon: "◧" },
  { to: "/search", label: "Search", icon: "⌕" },
  { to: "/companies", label: "Companies", icon: "▤" },
  { to: "/graph", label: "Entity graph", icon: "◬" },
  { to: "/portfolio", label: "Portfolio", icon: "▣" },
  { to: "/alerts", label: "Alerts", icon: "🔔" },
  { to: "/watchlists", label: "Watchlists", icon: "◎" },
  { to: "/workspaces", label: "Workspaces", icon: "❏" },
  { to: "/documents", label: "Documents", icon: "▦" },
  { to: "/compare", label: "Compare", icon: "⇄" },
  { to: "/sources", label: "Sources", icon: "⌥" },
  { to: "/monitoring", label: "Monitoring", icon: "◉" },
  { to: "/admin", label: "Admin", icon: "⌘" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

const CRUMBS: Array<[RegExp, string]> = [
  [/^\/world/, "World markets"],
  [/^\/country/, "Country exposure"],
  [/^\/atlas/, "Company graph"],
  [/^\/dashboard/, "Dashboard"],
  [/^\/search/, "Search the evidence"],
  [/^\/companies\/.+/, "Company"],
  [/^\/companies$/, "Companies"],
  [/^\/graph/, "Entity graph"],
  [/^\/portfolio/, "Portfolio"],
  [/^\/alerts/, "Alerts"],
  [/^\/watchlists/, "Watchlists"],
  [/^\/workspaces/, "Workspaces"],
  [/^\/documents\/.+/, "Document"],
  [/^\/documents$/, "Documents"],
  [/^\/compare/, "Compare documents"],
  [/^\/sources$/, "Sources"],
  [/^\/monitoring/, "Source monitoring"],
  [/^\/admin/, "Admin console"],
  [/^\/settings/, "Settings"],
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

function NotificationBell() {
  const location = useLocation();
  const [tick, setTick] = useState(0);
  // Refresh on navigation, and whenever an alerts mutation broadcasts a change.
  useEffect(() => {
    const handler = () => setTick((t) => t + 1);
    window.addEventListener(NOTIFICATIONS_EVENT, handler);
    return () => window.removeEventListener(NOTIFICATIONS_EVENT, handler);
  }, []);
  const { data } = useAsync(() => api.notificationsSummary(), [location.pathname, tick]);
  const unread = data?.unread ?? 0;
  return (
    <NavLink
      to="/alerts"
      className={({ isActive }) => (isActive ? "bell active" : "bell")}
      aria-label={unread > 0 ? `Alerts, ${unread} unread` : "Alerts"}
      title={unread > 0 ? `${unread} unread alert${unread === 1 ? "" : "s"}` : "Alerts"}
    >
      <span aria-hidden="true">🔔</span>
      {unread > 0 ? <span className="bell-badge">{unread > 99 ? "99+" : unread}</span> : null}
    </NavLink>
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
  // Atlas and World are full-bleed spatial surfaces: they opt out of the centered,
  // padded content column so the canvas/globe fills the viewport.
  const fullBleed = /^\/(atlas|world)/.test(location.pathname);

  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/world" className="brand">
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
            <NotificationBell />
            <span className="pill accent" title={email}>
              {email}
            </span>
            <button className="btn ghost" onClick={logout} style={{ padding: "6px 12px" }}>
              Sign out
            </button>
          </div>
        </header>
        <div className={fullBleed ? "content content-full" : "content"}>
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
        <Route path="/world" element={<WorldPage />} />
        <Route path="/country" element={<CountryPage />} />
        <Route path="/atlas" element={<AtlasPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/search" element={<AskPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/companies/:slug" element={<CompanyDetailPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/watchlists" element={<WatchlistsPage />} />
        <Route path="/workspaces" element={<WorkspacesPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/documents/:id" element={<DocumentDetailPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
