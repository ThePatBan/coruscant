// A small auto-rotating orthographic globe for the dashboard's "Live signals"
// panel. Coastlines from the shared Natural-Earth geometry, a graticule, and a
// rim glow — a spatial affordance that links to the full World view. No pins:
// the graph does not geo-tag signals, so we never plant fabricated ones.

import { useEffect, useRef } from "react";
import { WORLD_RINGS } from "./worldgeo";

const cssVar = (cs: CSSStyleDeclaration, name: string, fallback: string): string =>
  cs.getPropertyValue(name).trim() || fallback;

export function SignalGlobe() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cvs = ref.current;
    if (!cvs) return;
    let raf = 0;
    let alive = true;
    let theta = 0;
    let last = 0;
    const reduce = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const draw = (t: number) => {
      if (!alive) return;
      const dt = last ? Math.min(60, t - last) : 16;
      last = t;
      if (!reduce) theta += dt * 0.00016;

      const dpr = Math.min(2, window.devicePixelRatio || 1);
      let w = cvs.clientWidth;
      let h = cvs.clientHeight;
      if (!w || !h) {
        const p = cvs.parentElement;
        w = p?.clientWidth || 300;
        h = p?.clientHeight || 190;
      }
      if (cvs.width !== Math.round(w * dpr) || cvs.height !== Math.round(h * dpr)) {
        cvs.width = Math.round(w * dpr);
        cvs.height = Math.round(h * dpr);
      }
      const ctx = cvs.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const cs = getComputedStyle(cvs);
      const line = cssVar(cs, "--accent", "#7c8cff");
      const rim = cssVar(cs, "--accent-border", "rgba(124,140,255,.35)");

      const cx = w / 2;
      const cy = h / 2;
      const R = Math.min(w, h) / 2 - 10;
      const proj = (lat: number, lon: number) => {
        const ph = (lat * Math.PI) / 180;
        const la = (lon * Math.PI) / 180 + theta;
        return { x: cx + R * Math.cos(ph) * Math.sin(la), y: cy - R * Math.sin(ph), z: Math.cos(ph) * Math.cos(la) };
      };

      // sphere
      const grad = ctx.createRadialGradient(cx - R * 0.35, cy - R * 0.4, R * 0.15, cx, cy, R);
      grad.addColorStop(0, "#182231");
      grad.addColorStop(1, "#0b111b");
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.clip();

      // graticule
      ctx.strokeStyle = line;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.18;
      for (let lat = -60; lat <= 60; lat += 30) {
        let st = false;
        ctx.beginPath();
        for (let lon = -180; lon <= 180; lon += 6) {
          const p = proj(lat, lon);
          if (p.z > 0) {
            if (!st) { ctx.moveTo(p.x, p.y); st = true; } else ctx.lineTo(p.x, p.y);
          } else st = false;
        }
        ctx.stroke();
      }
      for (let lon = 0; lon < 180; lon += 30) {
        let st = false;
        ctx.beginPath();
        for (let lat = -90; lat <= 90; lat += 6) {
          const p = proj(lat, lon);
          if (p.z > 0) {
            if (!st) { ctx.moveTo(p.x, p.y); st = true; } else ctx.lineTo(p.x, p.y);
          } else st = false;
        }
        ctx.stroke();
      }

      // coastlines
      ctx.strokeStyle = line;
      ctx.globalAlpha = 0.4;
      ctx.lineWidth = 0.7;
      ctx.lineJoin = "round";
      for (const ring of WORLD_RINGS) {
        let st = false;
        ctx.beginPath();
        for (let i = 0; i < ring.length; i++) {
          const p = proj(ring[i][1], ring[i][0]);
          if (p.z > 0) {
            if (!st) { ctx.moveTo(p.x, p.y); st = true; } else ctx.lineTo(p.x, p.y);
          } else st = false;
        }
        ctx.stroke();
      }
      ctx.restore();

      // rim
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = rim;
      ctx.stroke();

      if (!reduce) raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      alive = false;
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={ref} className="orient-globe-canvas" />;
}
