import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, NOTIFICATIONS_EVENT } from "./api";
import { useAuth } from "./auth";
import { useAsync } from "./hooks";
import {
  IconBell,
  IconCard,
  IconChevrons,
  IconGear,
  IconLogout,
  IconShield,
} from "./icons";
import { resolveHomeWorkspace, routeAccess, WORKSPACES, workspaceForPath, workspaceStore } from "./workspaces";
import { AdminPage } from "./pages/AdminPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AtlasStakeholderPage } from "./pages/AtlasStakeholderPage";
import { AskPage } from "./pages/AskPage";
import { ChangesPage } from "./pages/ChangesPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyDetailPage } from "./pages/CompanyDetailPage";
import { ComparePage } from "./pages/ComparePage";
import { CountryPage } from "./pages/CountryPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EnterprisePage } from "./pages/EnterprisePage";
import { RiskPage } from "./pages/RiskPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { GraphPage } from "./pages/GraphPage";
import { LandingPage } from "./pages/LandingPage";
import { LiveSignalsPage } from "./pages/LiveSignalsPage";
import { LoginPage } from "./pages/LoginPage";
import { MonitoringPage } from "./pages/MonitoringPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { PublicHomePage } from "./pages/PublicHomePage";
import { SettingsPage } from "./pages/SettingsPage";
import { SourcesPage } from "./pages/SourcesPage";
import { WatchlistsPage } from "./pages/WatchlistsPage";
import { WorkspacesPage } from "./pages/WorkspacesPage";

// Platform vs workspace (see docs/PLATFORM.md): the app SHELL — auth, health pills,
// notifications, the user menu, /settings, /admin — is a PLATFORM surface shared by
// every workspace. The primary nav per workspace (Public / Personal / Enterprise) is
// defined once in workspaces.ts and rendered by the shared shell below, so the three
// products stay visually cohesive while feeling distinct.

// Breadcrumbs drive the browser tab title. Most specific patterns first.
const CRUMBS: Array<[RegExp, string]> = [
  [/^\/enterprise\/collaboration/, "Collaboration"],
  [/^\/enterprise\/sources/, "Data sources"],
  [/^\/enterprise\/monitoring/, "Monitoring"],
  [/^\/enterprise\/api/, "API & access"],
  [/^\/enterprise\/policy/, "Policy & audit"],
  [/^\/enterprise/, "Enterprise"],
  [/^\/public/, "Discover"],
  [/^\/world/, "Live signals"],
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

type Theme = "dark" | "light";

/** Shared dark/light theme state, persisted and applied to <html>. */
function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() =>
    (typeof localStorage !== "undefined" && localStorage.getItem("coruscant.theme")) === "light"
      ? "light"
      : "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("coruscant.theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return [theme, setTheme];
}

/** Collapsible-nav state, persisted across sessions. */
function useNavCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState<boolean>(
    () => (typeof localStorage !== "undefined" && localStorage.getItem("coruscant.navCollapsed")) === "1",
  );
  useEffect(() => {
    try {
      localStorage.setItem("coruscant.navCollapsed", collapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [collapsed]);
  return [collapsed, () => setCollapsed((c) => !c)];
}

function useDocumentTitle(pathname: string) {
  const crumb = CRUMBS.find(([re]) => re.test(pathname))?.[1] ?? "";
  useEffect(() => {
    document.title = crumb ? `Coruscant · ${crumb}` : "Coruscant";
  }, [crumb]);
}

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
      <IconBell />
      {unread > 0 ? <span className="bell-badge">{unread > 99 ? "99+" : unread}</span> : null}
    </NavLink>
  );
}

function ThemeToggle({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  return (
    <div className="segmented" role="group" aria-label="Appearance">
      <button className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")}>Dark</button>
      <button className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")}>Light</button>
    </div>
  );
}

function UserMenu({
  email,
  role,
  theme,
  setTheme,
  onLogout,
}: {
  email: string;
  role: string | null;
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
            <ThemeToggle theme={theme} setTheme={setTheme} />
          </div>

          <div className="usermenu-links">
            <NavLink to="/" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
              <IconChevrons /> Switch workspace
            </NavLink>
            <NavLink to="/settings" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
              <IconGear /> Settings
            </NavLink>
            <NavLink to="/settings" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
              <IconCard /> Plan &amp; usage
            </NavLink>
            {role === "admin" ? (
              <NavLink to="/admin" className="usermenu-item" role="menuitem" onClick={() => setOpen(false)}>
                <IconShield /> Admin console
              </NavLink>
            ) : null}
          </div>

          <button className="usermenu-item danger" role="menuitem" onClick={onLogout}>
            <IconLogout /> Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * The signed-in shell for the Personal and Enterprise workspaces. Which nav spine
 * and identity it shows is derived from the active route, so the two products share
 * one implementation while feeling distinct. All hooks run before the auth guards
 * so hook order stays stable across the loading → ready transition.
 */
function WorkspaceShell() {
  const { email, role, ready, logout } = useAuth();
  const location = useLocation();
  const [theme, setTheme] = useTheme();
  const [navCollapsed, toggleNav] = useNavCollapsed();
  useDocumentTitle(location.pathname);

  // Phase 6: an anonymous visitor is admitted to the curated public read surface
  // (routeAccess) and the shell then wears the Public identity + discovery nav for
  // them. A signed-in visitor gets the workspace that owns the path, unchanged.
  const anon = !email;
  const workspace = anon ? "public" : workspaceForPath(location.pathname);
  const ws = WORKSPACES[workspace];
  // Remember the active workspace so the home gate can bring the user back here —
  // but only once actually signed in, so a pre-redirect anonymous render doesn't
  // clobber the remembered choice.
  useEffect(() => {
    if (email) workspaceStore.set(workspace);
  }, [workspace, email]);

  if (!ready) {
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
        <span className="spinner" style={{ width: 26, height: 26 }} />
      </div>
    );
  }
  if (routeAccess(location.pathname, { authed: !anon }) === "requireLogin") {
    // Preserve the query string too, so a deep link like /search?q=… survives the
    // sign-in round-trip (the Public search box hands off here).
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  // Spatial surfaces opt out of the centered, padded content column so the
  // canvas/globe/wide layouts fill the viewport.
  const fullBleed = /^\/(atlas|world|dashboard|changes|risk|country)/.test(location.pathname);

  return (
    <div className={`app${navCollapsed ? " nav-collapsed" : ""}`}>
      <aside className="sidebar">
        <NavLink to={ws.home} className="brand" title="Coruscant">
          <div className="logo" />
          <div className="brand-text">
            <div className="name">Coruscant</div>
            <div className="tag">{ws.label}</div>
          </div>
        </NavLink>

        <nav className="nav">
          <div className="label">{ws.label} workspace</div>
          {ws.nav.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/enterprise"} title={item.label}>
              <item.Icon />
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="foot">
          <Link to="/" className="ws-switch">
            <IconChevrons /> <span className="nav-label">Switch workspace</span>
          </Link>
          <span className="ws-foot-note">Evidence-based intelligence. Every insight traces back to its source.</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button
            className="nav-toggle"
            onClick={toggleNav}
            title={navCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={navCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={navCollapsed}
          >
            <IconChevrons />
          </button>
          <div className="stats">
            <HealthPills />
            {email ? (
              <>
                <NotificationBell />
                <UserMenu email={email} role={role} theme={theme} setTheme={setTheme} onLogout={logout} />
              </>
            ) : (
              // Anonymous public browsing: no notifications/account menu — just the
              // appearance toggle and a sign-in that returns here after login.
              <>
                <ThemeToggle theme={theme} setTheme={setTheme} />
                <Link
                  className="btn ghost"
                  to="/login"
                  state={{ from: location.pathname + location.search }}
                >
                  Sign in
                </Link>
              </>
            )}
          </div>
        </header>
        <div className={fullBleed ? "content content-full" : "content"}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}

/**
 * The open shell for the free Public workspace. Same visual language as the signed-in
 * shell, but no auth guard and a discovery-only nav — opening a gated surface funnels
 * the visitor through sign-in.
 */
function PublicShell() {
  const { email } = useAuth();
  const location = useLocation();
  const [theme, setTheme] = useTheme();
  const [navCollapsed, toggleNav] = useNavCollapsed();
  useDocumentTitle(location.pathname);

  const ws = WORKSPACES.public;

  return (
    <div className={`app${navCollapsed ? " nav-collapsed" : ""}`}>
      <aside className="sidebar">
        <NavLink to="/public" className="brand" title="Coruscant">
          <div className="logo" />
          <div className="brand-text">
            <div className="name">Coruscant</div>
            <div className="tag">{ws.label}</div>
          </div>
        </NavLink>

        <nav className="nav">
          <div className="label">{ws.label} workspace</div>
          {ws.nav.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/public"} title={item.label}>
              <item.Icon />
              <span className="nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="foot">
          <Link to="/" className="ws-switch">
            <IconChevrons /> <span className="nav-label">Switch workspace</span>
          </Link>
          <span className="ws-foot-note">Free &amp; open. Sign in to unlock monitoring and portfolio.</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button
            className="nav-toggle"
            onClick={toggleNav}
            title={navCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={navCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={navCollapsed}
          >
            <IconChevrons />
          </button>
          <div className="stats">
            <HealthPills />
            <ThemeToggle theme={theme} setTheme={setTheme} />
            {email ? (
              <Link
                className="btn ghost"
                to={WORKSPACES[resolveHomeWorkspace({ authed: true, remembered: workspaceStore.get() })].home}
              >
                Open workspace →
              </Link>
            ) : (
              <Link className="btn ghost" to="/login">
                Sign in
              </Link>
            )}
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

      {/* Public workspace — free, open, discovery-first. No auth guard. */}
      <Route element={<PublicShell />}>
        <Route path="/public" element={<PublicHomePage />} />
      </Route>

      {/* Personal + Enterprise workspaces — the signed-in shell. */}
      <Route element={<WorkspaceShell />}>
        {/* Personal (monitoring) spine */}
        <Route path="/world" element={<LiveSignalsPage />} />
        <Route path="/country" element={<CountryPage />} />
        <Route path="/atlas" element={<AtlasStakeholderPage />} />
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

        {/* Enterprise workspace — org-level surfaces under a sticky /enterprise shell.
            Deep features reuse the existing platform pages. */}
        <Route path="/enterprise" element={<EnterprisePage />} />
        <Route path="/enterprise/collaboration" element={<WorkspacesPage />} />
        <Route path="/enterprise/sources" element={<SourcesPage />} />
        <Route path="/enterprise/monitoring" element={<MonitoringPage />} />
        <Route path="/enterprise/api" element={<SettingsPage />} />
        <Route path="/enterprise/policy" element={<AdminPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
