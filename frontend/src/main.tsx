import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import "./index.css";

// NOTE: React.StrictMode is intentionally omitted. The 3D Atlas
// (react-force-graph-3d / three) runs a WebGL animation loop that does not
// survive StrictMode's dev-only double-mount — it disposes the renderer between
// the discarded and real mount, and the orphaned animation frame then crashes.
// StrictMode is development-only, so this has no effect on production behaviour.
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <BrowserRouter>
    <AuthProvider>
      <App />
    </AuthProvider>
  </BrowserRouter>,
);
