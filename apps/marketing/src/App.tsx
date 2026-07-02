import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./Layout";
import { Home } from "./pages/Home";
import { AI } from "./pages/AI";
import { Public } from "./pages/Public";
import { Personal } from "./pages/Personal";
import { Enterprise } from "./pages/Enterprise";

// Marketing pages are full documents, so reset scroll on navigation.
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/ai" element={<AI />} />
          <Route path="/public" element={<Public />} />
          <Route path="/personal" element={<Personal />} />
          <Route path="/enterprise" element={<Enterprise />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
