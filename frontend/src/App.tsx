import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { useAsync } from "./hooks";
import { AskPage } from "./pages/AskPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { CompanyDetailPage } from "./pages/CompanyDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { SourcesPage } from "./pages/SourcesPage";

const NAV = [
  { to: "/", label: "Ask", icon: "◎", end: true },
  { to: "/companies", label: "Companies", icon: "▤", end: false },
  { to: "/documents", label: "Documents", icon: "▦", end: false },
  { to: "/sources", label: "Sources", icon: "⌥", end: false },
];

const CRUMBS: Array<[RegExp, string]> = [
  [/^\/$/, "Ask the evidence"],
  [/^\/companies\/.+/, "Company"],
  [/^\/companies$/, "Companies"],
  [/^\/documents\/.+/, "Document"],
  [/^\/documents$/, "Documents"],
  [/^\/sources$/, "Sources"],
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
  if (!data) {
    return (
      <span className="pill">
        <span className="spinner" style={{ width: 12, height: 12 }} />
      </span>
    );
  }
  return (
    <>
      <span className="pill">
        <span className="dot" />
        API healthy
      </span>
      <span className="pill accent">{data.documents} documents</span>
      <span className="pill">{data.graph_nodes} graph nodes</span>
    </>
  );
}

export default function App() {
  const location = useLocation();
  const crumb = CRUMBS.find(([re]) => re.test(location.pathname))?.[1] ?? "";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo" />
          <div>
            <div className="name">Coruscant</div>
            <div className="tag">Intelligence</div>
          </div>
        </div>

        <nav className="nav">
          <div className="label">Explore</div>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              <span className="ico">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="foot">
          Evidence-based financial &amp; corporate intelligence. Every answer traces back to a
          source.
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="crumb">{crumb}</div>
          <div className="stats">
            <HealthPills />
          </div>
        </header>

        <div className="content">
          <Routes>
            <Route path="/" element={<AskPage />} />
            <Route path="/companies" element={<CompaniesPage />} />
            <Route path="/companies/:slug" element={<CompanyDetailPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/documents/:id" element={<DocumentDetailPage />} />
            <Route path="/sources" element={<SourcesPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
