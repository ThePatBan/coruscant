// Minimal shared primitives for the admin app, using the same design-system classes
// as the console (index.css is copied verbatim). Kept small on purpose — only what the
// admin surfaces render.

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner" />
      {label}…
    </div>
  );
}
