// The Home globe — an auto-rotating world of markets (react-globe.gl / three).
// Countries render as dotted hex-polygons; each major exchange is a point lit
// green when it is open right now (computed from its local trading hours) and
// dim when closed. Clicking a market flies the camera to it and raises the
// country panel; clicking empty space resumes the rotation.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe from "react-globe.gl";
import { feature } from "topojson-client";
import landTopo from "world-atlas/countries-110m.json";
import { EXCHANGES, marketStatus, type Exchange } from "./world/exchanges";

// Country outlines for the dotted-globe surface (TopoJSON -> GeoJSON features).
const COUNTRIES = (
  feature(landTopo as never, (landTopo as never as { objects: { countries: never } }).objects.countries) as never as {
    features: unknown[];
  }
).features;

const esc = (s: string): string => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

interface MarketsGlobeProps {
  now: Date;
  selectedId?: string;
  onSelect: (ex: Exchange | null) => void;
}

export function MarketsGlobe({ now, selectedId, onSelect }: MarketsGlobeProps) {
  const globeRef = useRef<any>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 720, h: 560 });

  const points = useMemo(
    () => EXCHANGES.map((ex) => ({ ...ex, status: marketStatus(ex, now) })),
    [now],
  );

  // Fill the container.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Dark ocean material + auto-rotate, once the globe instance exists.
  const onReady = useCallback(() => {
    const g = globeRef.current;
    if (!g) return;
    try {
      const mat = g.globeMaterial();
      mat.color.set("#0a1020");
      mat.emissive.set("#060a14");
      mat.shininess = 6;
    } catch {
      /* material not ready */
    }
    const controls = g.controls?.();
    if (controls) {
      controls.autoRotate = !selectedId;
      controls.autoRotateSpeed = 0.45;
      controls.enableZoom = true;
    }
    g.pointOfView({ lat: 20, lng: 10, altitude: 2.4 }, 0);
  }, [selectedId]);

  // Fly to the selected market (and pause rotation); resume on deselect.
  useEffect(() => {
    const g = globeRef.current;
    if (!g) return;
    const controls = g.controls?.();
    const sel = EXCHANGES.find((e) => e.id === selectedId);
    if (sel) {
      if (controls) controls.autoRotate = false;
      g.pointOfView({ lat: sel.lat, lng: sel.lng, altitude: 1.6 }, 900);
    } else {
      if (controls) controls.autoRotate = true;
      g.pointOfView({ lat: 20, lng: 10, altitude: 2.4 }, 900);
    }
  }, [selectedId]);

  return (
    <div ref={wrapRef} className="markets-globe">
      <Globe
        ref={globeRef}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        animateIn={false}
        onGlobeReady={onReady}
        showAtmosphere
        atmosphereColor="#5b8ed0"
        atmosphereAltitude={0.16}
        hexPolygonsData={COUNTRIES as object[]}
        hexPolygonResolution={3}
        hexPolygonMargin={0.42}
        hexPolygonUseDots
        hexPolygonAltitude={0.005}
        hexPolygonColor={() => "rgba(120,162,222,0.42)"}
        pointsData={points}
        pointLat={(d: any) => d.lat}
        pointLng={(d: any) => d.lng}
        pointColor={(d: any) => (d.id === selectedId ? "#ffd66b" : d.status === "open" ? "#3ad29f" : "#5a647c")}
        pointAltitude={(d: any) => (d.status === "open" ? 0.07 : 0.025)}
        pointRadius={(d: any) => (d.id === selectedId ? 0.6 : 0.42)}
        pointResolution={18}
        pointLabel={(d: any) =>
          `<div class="globe-tip"><strong>${d.flag} ${esc(d.short)}</strong>` +
          `<span>${esc(d.city)} · ${d.status === "open" ? "OPEN" : "closed"}</span></div>`
        }
        pointsMerge={false}
        onPointClick={(d: any) => onSelect(EXCHANGES.find((e) => e.id === d.id) ?? null)}
        onGlobeClick={() => onSelect(null)}
      />
    </div>
  );
}
