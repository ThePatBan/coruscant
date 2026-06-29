import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type Workspace } from "../api";
import { Empty, Loading } from "../components";

const ITEM_TYPES = ["note", "thesis", "bookmark", "collection", "comment"];

export function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [active, setActive] = useState<Workspace | null>(null);
  const [name, setName] = useState("Research");
  const [members, setMembers] = useState("");
  const [item, setItem] = useState({ type: "note", title: "", body: "" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const guard = useCallback(async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    }
  }, []);

  const reload = useCallback(async () => {
    setError(null);
    try {
      setWorkspaces(await api.workspaces());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);

  const open = (id: string) => guard(async () => setActive(await api.workspace(id)));

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    const emails = members.split(",").map((m) => m.trim().toLowerCase()).filter(Boolean);
    await guard(async () => {
      await api.createWorkspace(name.trim(), emails);
      setName("Research");
      setMembers("");
      await reload();
    });
  }

  async function addItem(e: FormEvent) {
    e.preventDefault();
    if (!active || !item.title.trim()) return;
    const activeId = active.id;
    await guard(async () => {
      await api.addWorkspaceItem(activeId, item);
      setItem({ type: "note", title: "", body: "" });
      setActive(await api.workspace(activeId));
    });
  }

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Workspaces</h1>
        <p className="sub">
          Shared research for your team — notes, theses, bookmarks, and collections. Add members by
          email; everyone in a workspace sees its content.
        </p>
      </div>

      {loading ? <Loading label="Loading workspaces" /> : null}
      {error ? <div className="errbox">{error}</div> : null}

      <div className="grid cols-2">
        <form className="card stack gap" onSubmit={create}>
          <h2>New workspace</h2>
          <div className="field">
            <label>Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label>Members (comma-separated emails)</label>
            <input className="input" value={members} onChange={(e) => setMembers(e.target.value)} placeholder="teammate@firm.com" />
          </div>
          <button className="btn" type="submit">Create workspace</button>
        </form>

        <div className="stack gap">
          <h2>Your workspaces</h2>
          {workspaces.length === 0 ? (
            <Empty title="No workspaces yet" />
          ) : (
            workspaces.map((w) => (
              <button
                key={w.id}
                className="card hover row-between"
                style={{ textAlign: "left", cursor: "pointer", border: active?.id === w.id ? "1px solid var(--accent-border)" : undefined }}
                onClick={() => void open(w.id)}
              >
                <div>
                  <div style={{ fontWeight: 560 }}>{w.name}</div>
                  <div className="faint" style={{ fontSize: 12.5 }}>{w.members.length} member(s)</div>
                </div>
                <span className="faint">→</span>
              </button>
            ))
          )}
        </div>
      </div>

      {active ? (
        <div className="stack gap">
          <div className="row-between">
            <h2>{active.name}</h2>
            <span className="faint" style={{ fontSize: 12.5 }}>{active.members.join(", ")}</span>
          </div>

          <form className="card wrap" style={{ gap: 8 }} onSubmit={addItem}>
            <select className="input" value={item.type} onChange={(e) => setItem({ ...item, type: e.target.value })}>
              {ITEM_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input className="input" style={{ flex: 1, minWidth: 160 }} placeholder="Title" value={item.title} onChange={(e) => setItem({ ...item, title: e.target.value })} />
            <input className="input" style={{ flex: 2, minWidth: 200 }} placeholder="Note / thesis body" value={item.body} onChange={(e) => setItem({ ...item, body: e.target.value })} />
            <button className="btn" type="submit">Add</button>
          </form>

          {active.items.length === 0 ? (
            <Empty title="No items yet" hint="Add a note or thesis above." />
          ) : (
            <div className="list">
              {active.items.map((it) => (
                <div className="li" key={it.id} style={{ cursor: "default" }}>
                  <div className="grow">
                    <div className="wrap" style={{ gap: 8 }}>
                      <span className="badge">{it.type}</span>
                      <span style={{ fontWeight: 560 }}>{it.title}</span>
                    </div>
                    {it.body ? <div className="faint" style={{ fontSize: 13 }}>{it.body}</div> : null}
                    <div className="faint" style={{ fontSize: 11.5 }}>{it.author_email}</div>
                  </div>
                  <button
                    className="btn ghost"
                    style={{ padding: "5px 10px" }}
                    onClick={async () => {
                      await api.deleteWorkspaceItem(active.id, it.id);
                      await open(active.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
