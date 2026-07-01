# Frontend

The Coruscant SPA — **React + Vite + TypeScript**. Two tabs:

- **`/world`** — Home/World: portfolio summary + live prices, the react-globe.gl
  markets globe, the news rail, and portfolio composition (MSCI tiers, GICS tree,
  sector-vs-index benchmark, commodity exposure) + per-country macro/debt.
- **`/atlas`** — the 3D company graph (react-force-graph-3d).

Key files: `src/App.tsx`, `src/pages/WorldPage.tsx`, `src/MarketsGlobe.tsx`,
`src/Atlas3D.tsx`, `src/api.ts` (typed API client), `src/index.css` (the design
system — see [../DESIGN.md](../DESIGN.md)).

## Run

```bash
npm install
npm run dev     # SPA on :5173, proxies /api -> :8000
npm run build   # type-check + production build
```

The API must be running (`make api` from the repo root, on :8000). A `Dockerfile`
+ `nginx.conf` serve the built SPA and reverse-proxy `/api` in the docker stack.
