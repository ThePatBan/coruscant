// A focused, canvas-drawn country map. Reuses the shared Natural-Earth geometry
// (worldgeo.ts), projects it to the country's bounding box (equirectangular with
// a mid-latitude aspect correction), and pulses a centroid marker so the eye
// lands on the country in question. No fabricated signal pins — the graph does
// not geo-tag events, so we mark only the country itself.

import { useEffect, useRef } from "react";
import { WORLD_RINGS } from "./worldgeo";

export interface CountryView {
  lon0: number;
  lon1: number;
  lat0: number;
  lat1: number;
}

interface CountryMapProps {
  view: CountryView;
  centroid: { lat: number; lon: number };
  /** Cache-buster so the draw loop re-reads CSS vars after a resize/nav. */
  redrawKey?: string;
}

const cssVar = (cs: CSSStyleDeclaration, name: string, fallback: string): string =>
  cs.getPropertyValue(name).trim() || fallback;

export function CountryMap({ view, centroid, redrawKey }: CountryMapProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cvs = ref.current;
    if (!cvs) return;
    let raf = 0;
    let alive = true;
    const reduce = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const draw = (t: number) => {
      if (!alive) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      let w = cvs.clientWidth;
      let h = cvs.clientHeight;
      if (!w || !h) {
        const p = cvs.parentElement;
        w = p?.clientWidth || 800;
        h = p?.clientHeight || 360;
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
      const coast = cssVar(cs, "--accent", "#7c8cff");
      const grid = cssVar(cs, "--border", "#232a35");
      const accent = cssVar(cs, "--accent", "#7c8cff");

      const pad = 18;
      const lonSpan = view.lon1 - view.lon0;
      const latSpan = view.lat1 - view.lat0;
      const kx = (view.lat0 + view.lat1) / 2;
      const cosk = Math.cos((kx * Math.PI) / 360);
      const sc = Math.min((w - 2 * pad) / lonSpan, (h - 2 * pad) / (latSpan / cosk));
      const mapW = lonSpan * sc;
      const mapH = (latSpan / cosk) * sc;
      const ox = (w - mapW) / 2;
      const oy = (h - mapH) / 2;
      const proj = (lat: number, lon: number) => ({
        x: ox + (lon - view.lon0) * sc,
        y: oy + ((view.lat1 - lat) / cosk) * sc,
      });

      // graticule
      ctx.strokeStyle = grid;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.6;
      for (let lon = Math.ceil(view.lon0 / 10) * 10; lon <= view.lon1; lon += 10) {
        const a = proj(view.lat0, lon);
        const b = proj(view.lat1, lon);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      for (let lat = Math.ceil(view.lat0 / 10) * 10; lat <= view.lat1; lat += 10) {
        const a = proj(lat, view.lon0);
        const b = proj(lat, view.lon1);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // land outlines, clipped to the frame
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, w, h);
      ctx.clip();
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.strokeStyle = coast;
      ctx.lineWidth = 0.9;
      ctx.globalAlpha = 0.55;
      for (const ring of WORLD_RINGS) {
        // cheap cull: skip rings entirely outside the padded view
        let anyIn = false;
        for (let i = 0; i < ring.length; i += 4) {
          const [lon, lat] = ring[i];
          if (lon >= view.lon0 - 8 && lon <= view.lon1 + 8 && lat >= view.lat0 - 8 && lat <= view.lat1 + 8) {
            anyIn = true;
            break;
          }
        }
        if (!anyIn) continue;
        ctx.beginPath();
        for (let i = 0; i < ring.length; i++) {
          const p = proj(ring[i][1], ring[i][0]);
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
      }
      ctx.restore();

      // centroid pulse
      const cp = proj(centroid.lat, centroid.lon);
      const pulse = reduce ? 0.5 : 0.5 + 0.5 * Math.sin(t * 0.004);
      ctx.beginPath();
      ctx.arc(cp.x, cp.y, 22 + 8 * pulse, 0, Math.PI * 2);
      ctx.strokeStyle = accent;
      ctx.globalAlpha = 0.22 * (1 - pulse * 0.5);
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.save();
      ctx.shadowColor = accent;
      ctx.shadowBlur = 12;
      ctx.beginPath();
      ctx.arc(cp.x, cp.y, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = accent;
      ctx.fill();
      ctx.restore();

      if (!reduce) raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => {
      alive = false;
      if (raf) cancelAnimationFrame(raf);
    };
  }, [view, centroid, redrawKey]);

  return <canvas ref={ref} className="dp-mapcanvas" />;
}
