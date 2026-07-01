// A single cohesive line-icon set (inline SVG, no dependency) for the nav, top
// bar and profile menu. Geometric, 1.7px stroke, currentColor — tuned to the
// intelligence-terminal aesthetic so nothing reads like a stray Unicode glyph.

import type { SVGProps } from "react";

function Svg({ children, ...p }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={18}
      height={18}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...p}
    >
      {children}
    </svg>
  );
}

export type Icon = (p: SVGProps<SVGSVGElement>) => JSX.Element;

// Orientation dashboard — a panel/layout split.
export const IconDashboard: Icon = (p) => (
  <Svg {...p}>
    <rect x="3" y="3" width="18" height="18" rx="2.5" />
    <line x1="9" y1="3.5" x2="9" y2="20.5" />
    <line x1="9" y1="12" x2="21" y2="12" />
  </Svg>
);

// What changed — a commit dot on a line.
export const IconChanged: Icon = (p) => (
  <Svg {...p}>
    <line x1="3" y1="12" x2="8.3" y2="12" />
    <circle cx="12" cy="12" r="3.2" />
    <line x1="15.7" y1="12" x2="21" y2="12" />
  </Svg>
);

// Live signals — a globe.
export const IconSignals: Icon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <ellipse cx="12" cy="12" rx="4" ry="9" />
    <line x1="3" y1="12" x2="21" y2="12" />
  </Svg>
);

// Risk concentration — a heat grid.
export const IconRisk: Icon = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.2" fill="currentColor" stroke="none" opacity="0.32" />
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.2" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.2" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.2" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.2" />
  </Svg>
);

// Country — a map pin.
export const IconCountry: Icon = (p) => (
  <Svg {...p}>
    <path d="M12 21c4.2-4.2 6.5-7.6 6.5-10.5a6.5 6.5 0 0 0-13 0C5.5 13.4 7.8 16.8 12 21z" />
    <circle cx="12" cy="10.3" r="2.4" />
  </Svg>
);

// Company graph — connected nodes.
export const IconCompany: Icon = (p) => (
  <Svg {...p}>
    <circle cx="6" cy="6.5" r="2.3" />
    <circle cx="18" cy="8" r="2.3" />
    <circle cx="11.5" cy="18" r="2.3" />
    <line x1="7.9" y1="7.7" x2="10.2" y2="15.9" />
    <line x1="8.1" y1="6.8" x2="15.7" y2="7.7" />
    <line x1="16.4" y1="9.8" x2="12.8" y2="16" />
  </Svg>
);

// Find — search.
export const IconFind: Icon = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <line x1="16.2" y1="16.2" x2="21" y2="21" />
  </Svg>
);

// Alerts — bell.
export const IconBell: Icon = (p) => (
  <Svg {...p}>
    <path d="M6 9a6 6 0 0 1 12 0c0 4.5 1.8 5.8 2.2 6.1a.4.4 0 0 1-.2.7H4a.4.4 0 0 1-.2-.7C4.2 14.8 6 13.5 6 9z" />
    <path d="M10 19a2 2 0 0 0 4 0" />
  </Svg>
);

// Collapse / expand the nav — double chevron (rotate via CSS when collapsed).
export const IconChevrons: Icon = (p) => (
  <Svg {...p}>
    <polyline points="11 7 6 12 11 17" />
    <polyline points="18 7 13 12 18 17" />
  </Svg>
);

export const IconGear: Icon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 3v2.2M12 18.8V21M4.2 7l1.9 1.1M17.9 15.9 19.8 17M4.2 17l1.9-1.1M17.9 8.1 19.8 7M3 12h2.2M18.8 12H21" />
  </Svg>
);

export const IconCard: Icon = (p) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2.5" />
    <line x1="3" y1="9.5" x2="21" y2="9.5" />
    <line x1="6.5" y1="14" x2="10.5" y2="14" />
  </Svg>
);

export const IconShield: Icon = (p) => (
  <Svg {...p}>
    <path d="M12 3l7 2.5v5.2c0 4.3-2.9 8.2-7 9.3-4.1-1.1-7-5-7-9.3V5.5L12 3z" />
  </Svg>
);

export const IconLogout: Icon = (p) => (
  <Svg {...p}>
    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
    <polyline points="10 8 14 12 10 16" />
    <line x1="14" y1="12" x2="4" y2="12" />
  </Svg>
);
