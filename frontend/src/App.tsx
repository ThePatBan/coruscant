import { useEffect, useRef, useState } from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, NOTIFICATIONS_EVENT } from "./api";
import { useAuth } from "./auth";
import { useAsync } from "./hooks";
import { AdminPage } from "./pages/AdminPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AtlasPage } from "./pages/AtlasPage";
import { AskPage } from "./pages/AskPage";
import { ChangesPage } from "./pages/ChangesPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyDetailPage } from "./pages/CompanyDetailPage";
import { ComparePage } from "./pages/ComparePage";
import { CountryPage } from "./pages/CountryPage";
import { DashboardPage } from "./pages/DashboardPage";
import { RiskPage } from "./pages/RiskPage";
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

// Primary nav = the design-pack product spine (World → Country → Company, plus
// the analytical reads). Legacy surfaces are archived from the nav below.
const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "◧" },
  { to: "/changes", label: "What changed", icon: "≢" },
  { to: "/world", label: "Live signals", icon: "◍" },
  { to: "/risk", label: "Risk concentration", icon: "▩" },
  { to: "/country", label: "Country", icon: "⬡" },
  { to: "/atlas", label: "Company graph", icon: "✦" },
  { to: "/search", label: "Find", icon: "⌕" },
];

// TODO(retire): legacy surfaces superseded by the design-pack product. They stay
// ROUTED (reachable by URL; Settings/Admin also reach via the profile menu, Alerts
// via the bell) but are pulled from the primary nav pending final review. Archive
// or delete these pages + routes once the new product is signed off:
//   /companies /graph /portfolio /watchlists /workspaces /documents /compare
//   /sources /monitoring   (+ their components under src/pages/)

const CRUMBS: Array<[RegExp, string]> = [
  [/^\/world/, "World markets"],
  [/^\/country/, "Country exposure"],
  [/^\/atlas/, "Company graph"],
  [/^\/dashboard/, "Dashboard"],
  [/^\/changes/, "What changed"],
  [/^\/search/, "Search the evidence"],
  [/^\/companies\/.+/, "Company"],
  [/^\/companies$/, "Companies"],
  [/^\/graph/, "Entity graph"],
  [/^\/portfolio/, "Portfolio"],
  [/^\/risk/, "Risk concentration"],
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

type Theme = "dark" | "light";

function UserMenu({
  email,
  theme,
  setTheme,
  onLogout,
}: {
  email: string;
  theme: Theme;
  setTheme: (t: Theme) => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const initials = (email.split("@")[0] || email).slice(0, 2).toUpperCase();

  return (
    <div className="usermenu" ref={ref}>
      <button
        className="usermenu-btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={email}
      >
        {initials}
      </button>
      {open ? (
        <div className="usermenu-pop" role="menu">
          <div className="usermenu-id">
            <div className="usermenu-avatar">{initials}</div>
            <div style={{ minWidth: 0 }}>
              <div className="usermenu-email" title={email}>{email}</div>
              <div className="usermenu-role mono">Signed in</div>
            </div>
          </div>

          <div className="usermenu-sec">
            <div className="usermenu-sec-l">Appearance</div>
            <div className="segmented">
              <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>Dark</button>
              <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>Light</button>
            </div>
          </div>

          <div className="usermenu-links">
            <NavLink to="/settings" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
              <span className="ico">⚙</span> Settings
            </NavLink>
            <NavLink to="/settings" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
              <span className="ico">◈</span> Billing &amp; subscription
            </NavLink>
            <NavLink to="/admin" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
              <span className="ico">⌘</span> Admin console
            </NavLink>
          </div>

          <button className="usermenu-item danger" role="menuitem" onClick={onLogout}>
            <span className="ico">⏻</span> Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ProtectedLayout() {
  const { email, ready, logout } = useAuth();
  const location = useLocation();
  const [theme, setTheme] = useState<Theme>(() =>
    (typeof localStorage !== "undefined" && localStorage.getItem("coruscant.theme")) === "light" ? "light" : "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("coruscant.theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

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
  // Spatial surfaces opt out of the centered, padded content column so the
  // canvas/globe/wide layouts fill the viewport (they carry their own padding via
  // .spatial-page, or a full-bleed canvas for atlas/world).
  const fullBleed = /^\/(atlas|world|dashboard|changes|risk|country)/.test(location.pathname);

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
            <UserMenu email={email} theme={theme} setTheme={setTheme} onLogout={logout} />
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
        <Route path="/changes" element={<ChangesPage />} />
        <Route path="/search" element={<AskPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/companies/:slug" element={<CompanyDetailPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/risk" element={<RiskPage />} />
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
