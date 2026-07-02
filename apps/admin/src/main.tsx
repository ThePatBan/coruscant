import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth";
import "./index.css";
import "./admin-shell.css";

// No router: the internal admin app is a single authenticated surface. The auth gate
// in App decides between the sign-in screen, a not-authorized notice, and the console.
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <AuthProvider>
    <App />
  </AuthProvider>,
);
