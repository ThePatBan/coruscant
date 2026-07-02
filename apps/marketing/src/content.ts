// Shared marketing copy, grounded in what the platform actually does today (see
// PRODUCT.md and the console's workspace definitions). Tone: precise, evidence-bound,
// no hype. Anything not yet built is labelled "planned" on the page, never sold as live.

export interface Product {
  key: "public" | "personal" | "enterprise";
  eyebrow: string;
  name: string;
  tagline: string;
  blurb: string;
  bullets: [string, string, string];
  path: string; // marketing route
}

export const PRODUCTS: Product[] = [
  {
    key: "public",
    eyebrow: "Free · no account needed",
    name: "Public Knowledge",
    tagline: "Explore the evidence graph, open to everyone.",
    blurb:
      "Search companies, trace relationships, and read source-linked disclosures. Every edge carries the filing or public classification behind it — nothing is inferred without a label.",
    bullets: [
      "Company profiles & entity search",
      "Relationship & ownership graph",
      "Source-linked evidence & timelines",
    ],
    path: "/public",
  },
  {
    key: "personal",
    eyebrow: "For individual investors & analysts",
    name: "Personal Console",
    tagline: "Turn discovery into monitoring.",
    blurb:
      "Watchlists, alerts, and portfolio-exposure analysis tuned to you. Trace a public event to the holdings it actually touches — geography, sector, market tier — and see what changed since you last looked.",
    bullets: [
      "Watchlists & saved searches",
      "Portfolio & exposure analysis",
      "Alerts on material change",
    ],
    path: "/personal",
  },
  {
    key: "enterprise",
    eyebrow: "For teams & organizations",
    name: "Enterprise Intelligence",
    tagline: "Org-level intelligence for your whole team.",
    blurb:
      "Shared research workspaces, organization administration, and programmatic access with scoped API keys — the platform's evidence graph, wired into how your team already works.",
    bullets: [
      "Shared workspaces & collaboration",
      "Scoped API keys & programmatic access",
      "Organization settings & members",
    ],
    path: "/enterprise",
  },
];

export function productByKey(key: Product["key"]): Product {
  const p = PRODUCTS.find((x) => x.key === key);
  if (!p) throw new Error(`unknown product: ${key}`);
  return p;
}

// Capabilities the AI surface actually provides today: grounded, source-cited answers
// over the evidence graph, with tiered model routing. Kept honest — it answers from the
// graph and cites sources; it does not invent facts.
export const AI_POINTS: { title: string; body: string }[] = [
  {
    title: "Grounded in the evidence graph",
    body: "Answers are built from the same source-linked graph you can browse — filings and public classifications, not open-web guesswork.",
  },
  {
    title: "Citations, enforced",
    body: "Every claim carries the source behind it. If the graph can't support a statement, the analyst says so instead of inventing one.",
  },
  {
    title: "Tiered model routing",
    body: "Cheap, local models handle bulk work; the most capable models are reserved for demanding synthesis — routed per task tier.",
  },
];

// Roadmap items — shown ONLY under an explicit "Planned" heading so nothing here reads
// as a shipping capability (private connectors, SSO, billing, UBO/PEP pathways).
export const PLANNED: { title: string; body: string }[] = [
  { title: "SSO & SCIM", body: "Org-managed identity, directory sync, and role provisioning." },
  { title: "Seats & billing", body: "Self-serve seat management, plan changes, and invoices." },
  { title: "Private connectors", body: "Bring your own filings, CRM, and internal documents into the graph." },
  { title: "Ownership & PEP pathways", body: "Beneficial-ownership groups and PEP/sanctions screening across the graph." },
];

// Honest coverage note — the graph is a curated sample, not exhaustive.
export const COVERAGE_NOTE =
  "Coverage today is a curated sample across US, UK, and India markets — companies, people, subsidiaries, sectors, market tiers, commodities, and debt — expanding over time.";
