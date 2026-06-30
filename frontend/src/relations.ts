// The relation visual-language. One place that maps the graph's raw relation
// strings to (a) a *tier* — the analytical meaning a reader scans for — and
// (b) the human verb shown in chips. Colors live in CSS keyed by `tier-<name>`
// so the map, chips, legend, and company page all read the same way.
//
// Grounded in the actual edges the backend projects (knowledge_graph/entities.py):
//   employs · previously_at · relies_on_supplier · operates_in · supplies_to ·
//   competes_with · partners_with · produces · uses_technology · engaged_with.
// There is deliberately NO ownership/parent/subsidiary edge — control is only
// ever inferred (see the "proxy" tier), never asserted.

export type RelationTier =
  | "control" // direct leadership of a company
  | "proxy" // inferred influence: leadership overlap, prior tenure, agency ties
  | "supply" // dependency / country exposure
  | "alliance" // partner / customer
  | "peer" // rivalry
  | "product" // builds / uses
  | "reference" // extracted at scale from filings: co-mention, shared sector
  | "mention";

interface RelationMeta {
  tier: RelationTier;
  /** verb reading source → target, e.g. Apple "supplied by" TSMC. */
  verb: string;
}

const RELATIONS: Record<string, RelationMeta> = {
  employs: { tier: "control", verb: "leads" },
  previously_at: { tier: "proxy", verb: "formerly at" },
  relies_on_supplier: { tier: "supply", verb: "supplied by" },
  operates_in: { tier: "supply", verb: "operates in" },
  supplies_to: { tier: "alliance", verb: "supplies" },
  competes_with: { tier: "peer", verb: "competes with" },
  partners_with: { tier: "alliance", verb: "partners with" },
  produces: { tier: "product", verb: "produces" },
  uses_technology: { tier: "product", verb: "uses" },
  engaged_with: { tier: "proxy", verb: "engaged with" },
  mentions: { tier: "mention", verb: "mentions" },
  // Extracted at scale from filings (provenance: the filing). references = company
  // A names company B; in_sector = SEC SIC classification.
  references: { tier: "reference", verb: "names in filings" },
  in_sector: { tier: "reference", verb: "in sector" },
};

const FALLBACK: RelationMeta = { tier: "peer", verb: "" };

// The meaningful *entity-to-entity* relations. Everything else a profile carries
// (`mentions`, and the document-linkage edges `filed` / `published`) connects a
// company to a document, not to another entity, so it is excluded from the
// relationship graph and the typed relationship views.
const ENTITY_RELATIONS = new Set([
  "employs",
  "previously_at",
  "relies_on_supplier",
  "operates_in",
  "supplies_to",
  "competes_with",
  "partners_with",
  "produces",
  "uses_technology",
  "engaged_with",
  "references",
  "in_sector",
]);

export function isEntityRelation(relation: string): boolean {
  return ENTITY_RELATIONS.has(relation);
}

export function relationMeta(relation: string): RelationMeta {
  return RELATIONS[relation] ?? { ...FALLBACK, verb: relation.replace(/_/g, " ") };
}

export function relationTier(relation: string): RelationTier {
  return relationMeta(relation).tier;
}

export function relationVerb(relation: string): string {
  return relationMeta(relation).verb || relation.replace(/_/g, " ");
}

export interface TierInfo {
  tier: RelationTier;
  label: string;
  hint: string;
}

// Legend order = reading priority. Control and its proxy first (the ownership
// question), then dependency, then the softer business ties.
export const TIERS: TierInfo[] = [
  { tier: "control", label: "Leadership", hint: "Direct control of a company" },
  { tier: "proxy", label: "Control by proxy", hint: "Inferred — leadership overlap or prior tenure" },
  { tier: "supply", label: "Supply exposure", hint: "Depends on a supplier or country" },
  { tier: "alliance", label: "Alliance", hint: "Partner or customer" },
  { tier: "peer", label: "Rivalry", hint: "Named competitor" },
  { tier: "product", label: "Product / tech", hint: "Builds or uses" },
  { tier: "reference", label: "Co-mention", hint: "Extracted from filings: names each other, or shared SIC sector" },
];

const TIER_LABELS: Record<RelationTier, string> = {
  control: "Leadership",
  proxy: "Control by proxy",
  supply: "Supply exposure",
  alliance: "Alliance",
  peer: "Rivalry",
  product: "Product / tech",
  reference: "Co-mention",
  mention: "Mention",
};

export function tierLabel(tier: RelationTier): string {
  return TIER_LABELS[tier];
}

// A short glyph per entity kind, used in nodes and chips. Kept monochrome and
// geometric to match the terminal aesthetic (no emoji in the data layer).
const KIND_GLYPHS: Record<string, string> = {
  Company: "◧",
  Person: "◍",
  Country: "⊕",
  Product: "▰",
  Technology: "⚙",
  Agency: "▣",
  Industry: "❖",
  Document: "▦",
};

export function kindGlyph(kind: string): string {
  return KIND_GLYPHS[kind] ?? "•";
}

// Map a granular SEC SIC industry description to a coarse sector, so companies
// cluster into readable groups on the canvas (exact SIC is mostly singletons).
// Order matters — earlier rules win.
const SECTOR_RULES: Array<[RegExp, string]> = [
  [/pharmaceut|biological|medical|hospital|health|surgical|diagnostic/, "Health"],
  [/bank|financ|insurance|broker|casualty|securit/, "Financials"],
  [/software|comput|semiconduct|communications equip|electronic|information|internet/, "Technology"],
  [/petroleum|oil|gas|energy|refin|coal|drilling/, "Energy"],
  [/telephone|telecom|wireless|broadcast/, "Telecom"],
  [/retail/, "Retail"],
  [/aircraft|machinery|construction|industrial|engine|aerospace|defense/, "Industrials"],
  [/beverage|food|soap|detergent|cosmetic|footwear|apparel|tobacco|household|amusement|recreation|motion picture|entertain/, "Consumer"],
];

export function coarseSector(industry: string | null | undefined): string {
  const s = (industry || "").toLowerCase();
  for (const [re, sector] of SECTOR_RULES) if (re.test(s)) return sector;
  return "Other";
}
