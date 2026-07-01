// Interactive orthographic globe for Live Signals. Real coastlines (shared
// worldgeo), a graticule, and signal pins geo-placed by HQ country. The globe
// eases its rotation to the selected signal, pins pulse, hover raises a label,
// and a click selects. Colors read from CSS vars so it re-themes with the app.

import { useEffect, useRef } from "react";
import { WORLD_RINGS } from "./worldgeo";

export interface GlobeSignal {
  id: string;
  lat: number;
  lon: number;
  cat: "risk" | "opp" | "event";
  label: string;
}

interface Props {
  signals: GlobeSignal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const V = (cs: CSSStyleDeclaration, n: string, f: string) => cs.getPropertyValue(n).trim() || f;

export function SignalsGlobe({ signals, selectedId, onSelect }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  // live-updated refs so the rAF loop always sees current props without restart
  const sigRef = useRef(signals);
  const selRef = useRef(selectedId);
  sigRef.current = signals;
  selRef.current = selectedId;

  useEffect(() => {
    const cvs = ref.current;
    if (!cvs) return;
    let raf = 0;
    let alive = true;
    let theta = 0;
    let last = 0;
    let hover: string | null = null;
    const reduce = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    const geom = () => {
      const w = cvs.clientWidth || 600;
      const h = cvs.clientHeight || 600;
      return { w, h, cx: w / 2, cy: h / 2, R: Math.min(w, h) / 2 - 26 };
    };
    const project = (g: ReturnType<typeof geom>, lat: number, lon: number) => {
      const ph = (lat * Math.PI) / 180;
      const la = (lon * Math.PI) / 180 + theta;
      return { x: g.cx + g.R * Math.cos(ph) * Math.sin(la), y: g.cy - g.R * Math.sin(ph), z: Math.cos(ph) * Math.cos(la) };
    };
    const hit = (mx: number, my: number): string | null => {
      const g = geom();
      let best: string | null = null;
      let bestD = 16;
      for (const s of sigRef.current) {
        const p = project(g, s.lat, s.lon);
        if (p.z <= 0.02) continue;
        const dd = Math.hypot(p.x - mx, p.y - my);
        if (dd < bestD) { bestD = dd; best = s.id; }
      }
      return best;
    };

    const onMove = (e: MouseEvent) => {
      const r = cvs.getBoundingClientRect();
      hover = hit(e.clientX - r.left, e.clientY - r.top);
      cvs.style.cursor = hover ? "pointer" : "grab";
    };
    const onLeave = () => { hover = null; };
    const onClick = (e: MouseEvent) => {
      const r = cvs.getBoundingClientRect();
      const id = hit(e.clientX - r.left, e.clientY - r.top);
      if (id) onSelect(id);
    };
    cvs.addEventListener("mousemove", onMove);
    cvs.addEventListener("mouseleave", onLeave);
    cvs.addEventListener("click", onClick);

    const draw = (t: number) => {
      if (!alive) return;
      const dt = last ? Math.min(60, t - last) : 16;
      last = t;

      // ease rotation toward the selected signal's longitude, else drift
      const sel = sigRef.current.find((s) => s.id === selRef.current);
      if (sel) {
        let d = -sel.lon * (Math.PI / 180) - theta;
        d = Math.atan2(Math.sin(d), Math.cos(d));
        theta += d * 0.09;
      } else if (!reduce) {
        theta += dt * 0.00012;
      }

      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = cvs.clientWidth || 600;
      const h = cvs.clientHeight || 600;
      if (cvs.width !== Math.round(w * dpr) || cvs.height !== Math.round(h * dpr)) {
        cvs.width = Math.round(w * dpr);
        cvs.height = Math.round(h * dpr);
      }
      const ctx = cvs.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const cs = getComputedStyle(cvs);
      const line = V(cs, "--accent", "#7c8cff");
      const rim = V(cs, "--accent-border", "rgba(124,140,255,.35)");
      const g1 = V(cs, "--globe-1", "#141d2b");
      const g2 = V(cs, "--globe-2", "#0a0f18");
      const col = {
        risk: V(cs, "--danger", "#ff6b6b"),
        opp: V(cs, "--good", "#4bd6a0"),
        event: V(cs, "--accent", "#7c8cff"),
      };
      const g = geom();

      // sphere
      const grad = ctx.createRadialGradient(g.cx - g.R * 0.35, g.cy - g.R * 0.4, g.R * 0.15, g.cx, g.cy, g.R);
      grad.addColorStop(0, g1);
      grad.addColorStop(1, g2);
      ctx.beginPath();
      ctx.arc(g.cx, g.cy, g.R, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.save();
      ctx.beginPath();
      ctx.arc(g.cx, g.cy, g.R, 0, Math.PI * 2);
      ctx.clip();

      ctx.strokeStyle = line;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.14;
      for (let lat = -60; lat <= 60; lat += 30) {
        let st = false;
        ctx.beginPath();
        for (let lon = -180; lon <= 180; lon += 6) {
          const p = project(g, lat, lon);
          if (p.z > 0) { if (!st) { ctx.moveTo(p.x, p.y); st = true; } else ctx.lineTo(p.x, p.y); } else st = false;
        }
        ctx.stroke();
      }
      for (let lon = 0; lon < 180; lon += 30) {
        let st = false;
        ctx.beginPath();
        for (let lat = -90; lat <= 90; lat += 6) {
          const p = project(g, lat, lon);
          if (p.z > 0) { if (!st) { ctx.moveTo(p.x, p.y); st = true; } else ctx.lineTo(p.x, p.y); } else st = false;
        }
        ctx.stroke();
      }

      ctx.strokeStyle = line;
      ctx.globalAlpha = 0.38;
      ctx.lineWidth = 0.7;
      ctx.lineJoin = "round";
      for (const ring of WORLD_RINGS) {
        let st = false;
        ctx.beginPath();
        for (let i = 0; i < ring.length; i++) {
          const p = project(g, ring[i][1], ring[i][0]);
          if (p.z > 0) { if (!st) { ctx.moveTo(p.x, p.y); st = true; } else ctx.lineTo(p.x, p.y); } else st = false;
        }
        ctx.stroke();
      }
      ctx.restore();

      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(g.cx, g.cy, g.R, 0, Math.PI * 2);
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = rim;
      ctx.stroke();

      // pins
      const pulse = 0.5 + 0.5 * Math.sin(t * 0.004);
      let labelAt: { x: number; y: number; text: string } | null = null;
      for (const s of sigRef.current) {
        const p = project(g, s.lat, s.lon);
        if (p.z <= 0.02) continue;
        const depth = 0.55 + 0.45 * p.z;
        const c = col[s.cat] || col.event;
        const on = s.id === selRef.current;
        const hv = s.id === hover;
        const base = 3.4 * depth;
        // pulse ring
        ctx.beginPath();
        ctx.arc(p.x, p.y, base * (1.7 + 1.3 * (1 - pulse)), 0, Math.PI * 2);
        ctx.strokeStyle = c;
        ctx.globalAlpha = 0.2 * pulse;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.globalAlpha = 1;
        if (on) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, base + 7 + 2 * pulse, 0, Math.PI * 2);
          ctx.strokeStyle = c;
          ctx.globalAlpha = 0.9;
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
        ctx.save();
        ctx.shadowColor = c;
        ctx.shadowBlur = (on || hv ? 16 : 9) * depth;
        ctx.beginPath();
        ctx.arc(p.x, p.y, base * (on ? 1.5 : hv ? 1.3 : 1), 0, Math.PI * 2);
        ctx.fillStyle = c;
        ctx.fill();
        ctx.restore();
        if (on || hv) labelAt = { x: p.x, y: p.y, text: s.label };
      }
      if (labelAt) {
        ctx.font = "600 11.5px ui-monospace, Menlo, monospace";
        const tw = ctx.measureText(labelAt.text).width;
        let lx = labelAt.x + 12;
        let ly = labelAt.y - 8;
        if (lx + tw + 16 > g.w) lx = labelAt.x - tw - 24;
        if (ly < 16) ly = 16;
        const bg = V(cs, "--bg-elev", "#11141a");
        const bd = V(cs, "--border", "#232a35");
        const tx = V(cs, "--text", "#e8ebef");
        ctx.fillStyle = bg;
        ctx.strokeStyle = bd;
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(lx - 8, ly - 14, tw + 16, 22, 6);
        else ctx.rect(lx - 8, ly - 14, tw + 16, 22);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = tx;
        ctx.fillText(labelAt.text, lx, ly + 1);
      }

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    return () => {
      alive = false;
      if (raf) cancelAnimationFrame(raf);
      cvs.removeEventListener("mousemove", onMove);
      cvs.removeEventListener("mouseleave", onLeave);
      cvs.removeEventListener("click", onClick);
    };
  }, [onSelect]);

  return <canvas ref={ref} className="ls-globe-canvas" />;
}
