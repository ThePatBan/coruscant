"""Curated, verifiable allocator taxonomy: the GICS hierarchy + MSCI market tiers.

The SEC SIC code a company self-reports (``CompanyConfig.industry``) is a
product/operations label — not how an allocator thinks about a book. This module
layers two public, allocator-standard classifications on top of it:

  * **GICS hierarchy** — the full four levels (sector -> industry group ->
    industry -> sub-industry), keyed by the **8-digit GICS code**. The code *is*
    the hierarchy: digits 1-2 = sector, 1-4 = industry group, 1-6 = industry, all
    8 = sub-industry. It re-tags the ``in_sector`` edge so the taxonomy-agnostic
    exposure engine can match an event at *any* level — "Semiconductors" hits only
    the chip names, not the whole tech sector. It is also the canonical anchor for
    joining a holding to its MSCI sector index for benchmarking.
  * **MSCI market classification** (Developed / Emerging / Frontier), keyed on the
    company's listing country — the market-tier exposure pathway ("you're 15% EM,
    heavy India"). Combined with the GICS sector it pins each holding to an MSCI
    slice (e.g. *MSCI EM Information Technology*).

This is *curated reference data*, not fabrication: every entry is a public,
widely published classification, verified against MSCI/S&P GICS sources. (The
March-2023 GICS revision is the trap to respect — it moved Visa/Mastercard from
IT to Financials and renumbered the retail industries.) Provenance rides every
projected edge as ``gics-curated`` / ``msci-classification``, distinct from the
filing-derived ``sec-metadata``. Only the sub-industries our tracked companies
actually map to are materialized here — the rest of the 163 stay absent rather
than fabricated, and "no exposure" is already a first-class answer; add a row
when a new holding needs it.
"""

from __future__ import annotations

from typing import NamedTuple

# The 11 canonical GICS sectors — the allocator's top-level lens.
GICS_SECTORS: tuple[str, ...] = (
    "Energy",
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Information Technology",
    "Communication Services",
    "Utilities",
    "Real Estate",
)

# MSCI market-classification labels (the code rides the edge; the label is for UX).
MSCI_TIER_LABELS: dict[str, str] = {
    "DM": "Developed market",
    "EM": "Emerging market",
    "FM": "Frontier market",
}


class GicsNode(NamedTuple):
    """One node of the GICS hierarchy, addressed by its 8-digit sub-industry code.
    The four names are the path from sector down to sub-industry."""

    code: str  # 8-digit GICS sub-industry code (e.g. "45301020" Semiconductors)
    sector: str  # one of GICS_SECTORS
    industry_group: str
    industry: str
    sub_industry: str


# The GICS sub-industries the tracked companies map to, keyed by 8-digit code.
# Verified against public MSCI/S&P GICS materials (post the March-2023 revision).
GICS_SUB_INDUSTRIES: dict[str, GicsNode] = {
    "10102010": GicsNode("10102010", "Energy", "Energy", "Oil, Gas & Consumable Fuels", "Integrated Oil & Gas"),
    "15101050": GicsNode("15101050", "Materials", "Materials", "Chemicals", "Specialty Chemicals"),
    "15104020": GicsNode("15104020", "Materials", "Materials", "Metals & Mining", "Diversified Metals & Mining"),
    "20101010": GicsNode("20101010", "Industrials", "Capital Goods", "Aerospace & Defense", "Aerospace & Defense"),
    "20105010": GicsNode("20105010", "Industrials", "Capital Goods", "Industrial Conglomerates", "Industrial Conglomerates"),
    "20106010": GicsNode("20106010", "Industrials", "Capital Goods", "Machinery", "Construction Machinery & Heavy Transportation Equipment"),
    "20202020": GicsNode("20202020", "Industrials", "Commercial & Professional Services", "Professional Services", "Research & Consulting Services"),
    "25203020": GicsNode("25203020", "Consumer Discretionary", "Consumer Durables & Apparel", "Textiles, Apparel & Luxury Goods", "Footwear"),
    "25301020": GicsNode("25301020", "Consumer Discretionary", "Consumer Services", "Hotels, Restaurants & Leisure", "Hotels, Resorts & Cruise Lines"),
    "25301040": GicsNode("25301040", "Consumer Discretionary", "Consumer Services", "Hotels, Restaurants & Leisure", "Restaurants"),
    "25503030": GicsNode("25503030", "Consumer Discretionary", "Consumer Discretionary Distribution & Retail", "Broadline Retail", "Broadline Retail"),
    "25504030": GicsNode("25504030", "Consumer Discretionary", "Consumer Discretionary Distribution & Retail", "Specialty Retail", "Home Improvement Retail"),
    "30101040": GicsNode("30101040", "Consumer Staples", "Consumer Staples Distribution & Retail", "Consumer Staples Distribution & Retail", "Consumer Staples Merchandise Retail"),
    "30201020": GicsNode("30201020", "Consumer Staples", "Food, Beverage & Tobacco", "Beverages", "Distillers & Vintners"),
    "30201030": GicsNode("30201030", "Consumer Staples", "Food, Beverage & Tobacco", "Beverages", "Soft Drinks & Non-alcoholic Beverages"),
    "30203010": GicsNode("30203010", "Consumer Staples", "Food, Beverage & Tobacco", "Tobacco", "Tobacco"),
    "30301010": GicsNode("30301010", "Consumer Staples", "Household & Personal Products", "Household Products", "Household Products"),
    "30302010": GicsNode("30302010", "Consumer Staples", "Household & Personal Products", "Personal Care Products", "Personal Care Products"),
    "35102030": GicsNode("35102030", "Health Care", "Health Care Equipment & Services", "Health Care Providers & Services", "Managed Health Care"),
    "35201010": GicsNode("35201010", "Health Care", "Pharmaceuticals, Biotechnology & Life Sciences", "Biotechnology", "Biotechnology"),
    "35202010": GicsNode("35202010", "Health Care", "Pharmaceuticals, Biotechnology & Life Sciences", "Pharmaceuticals", "Pharmaceuticals"),
    "40101010": GicsNode("40101010", "Financials", "Banks", "Banks", "Diversified Banks"),
    "40201060": GicsNode("40201060", "Financials", "Financial Services", "Financial Services", "Transaction & Payment Processing Services"),
    "40202010": GicsNode("40202010", "Financials", "Financial Services", "Consumer Finance", "Consumer Finance"),
    "40203020": GicsNode("40203020", "Financials", "Financial Services", "Capital Markets", "Investment Banking & Brokerage"),
    "40301020": GicsNode("40301020", "Financials", "Insurance", "Insurance", "Life & Health Insurance"),
    "40301040": GicsNode("40301040", "Financials", "Insurance", "Insurance", "Property & Casualty Insurance"),
    "45102010": GicsNode("45102010", "Information Technology", "Software & Services", "IT Services", "IT Consulting & Other Services"),
    "45103010": GicsNode("45103010", "Information Technology", "Software & Services", "Software", "Application Software"),
    "45103020": GicsNode("45103020", "Information Technology", "Software & Services", "Software", "Systems Software"),
    "45201020": GicsNode("45201020", "Information Technology", "Technology Hardware & Equipment", "Communications Equipment", "Communications Equipment"),
    "45202030": GicsNode("45202030", "Information Technology", "Technology Hardware & Equipment", "Technology Hardware, Storage & Peripherals", "Technology Hardware, Storage & Peripherals"),
    "45301020": GicsNode("45301020", "Information Technology", "Semiconductors & Semiconductor Equipment", "Semiconductors & Semiconductor Equipment", "Semiconductors"),
    "50101010": GicsNode("50101010", "Communication Services", "Telecommunication Services", "Diversified Telecommunication Services", "Alternative Carriers"),
    "50101020": GicsNode("50101020", "Communication Services", "Telecommunication Services", "Diversified Telecommunication Services", "Integrated Telecommunication Services"),
    "50102010": GicsNode("50102010", "Communication Services", "Telecommunication Services", "Wireless Telecommunication Services", "Wireless Telecommunication Services"),
    "50202010": GicsNode("50202010", "Communication Services", "Media & Entertainment", "Entertainment", "Movies & Entertainment"),
    "55103010": GicsNode("55103010", "Utilities", "Utilities", "Multi-Utilities", "Multi-Utilities"),
}

# slug -> 8-digit GICS sub-industry code. The code resolves to the full path via
# GICS_SUB_INDUSTRIES, so the hierarchy is stored once and referenced by code.
COMPANY_GICS_CODE: dict[str, str] = {
    # --- United States (Dow 30) ---
    "mmm": "20105010",
    "axp": "40202010",
    "amgn": "35201010",
    "amzn": "25503030",
    "aapl": "45202030",
    "ba": "20101010",
    "cat": "20106010",
    "cvx": "10102010",
    "csco": "45201020",
    "ko": "30201030",
    "dis": "50202010",
    "gs": "40203020",
    "hd": "25504030",
    "hon": "20105010",
    "ibm": "45102010",
    "jnj": "35202010",
    "jpm": "40101010",
    "mcd": "25301040",
    "mrk": "35202010",
    "msft": "45103020",
    "nke": "25203020",
    "nvda": "45301020",
    "pg": "30301010",
    "crm": "45103010",
    "shw": "15101050",
    "trv": "40301040",
    "unh": "35102030",
    "vz": "50101020",
    "v": "40201060",
    "wmt": "30101040",
    # --- United Kingdom (cross-listed 20-F filers) ---
    "shel": "10102010",
    "bp": "10102010",
    "azn": "35202010",
    "hsbc": "40101010",
    "ul": "30302010",
    "deo": "30201020",
    "bcs": "40101010",
    "rio": "15104020",
    "bti": "30203010",
    "vod": "50102010",
    "nwg": "40101010",
    "relx": "20202020",
    "ngg": "55103010",
    "gsk": "35202010",
    "puk": "40301020",
    # --- India (ADRs) ---
    "infy": "45102010",
    "wit": "45102010",
    "ibn": "40101010",
    "hdb": "40101010",
    "rdy": "35202010",
    # Sify is a *licensed Indian telecom/ICT carrier* (NLD/ILD/ISP licences), not a
    # software house — the SIC "Computer Programming" label is a trap.
    "sify": "50101010",
    "mmyt": "25301020",
    "ytra": "25301020",
}

# Listing country -> MSCI market classification. Keyed on the country string the
# config carries (and the same strings on has_subsidiary jurisdictions / the
# globe's exchange table), so the three taxonomies agree on country names.
COUNTRY_MSCI: dict[str, str] = {
    "United States": "DM",
    "United Kingdom": "DM",
    "India": "EM",
}


def company_gics(slug: str) -> GicsNode | None:
    """Full GICS path for a tracked company, or None if uncurated."""
    code = COMPANY_GICS_CODE.get(slug)
    return GICS_SUB_INDUSTRIES.get(code) if code else None


def country_msci_tier(country: str | None) -> str | None:
    """MSCI tier code (DM/EM/FM) for a listing country, or None if unmapped."""
    if not country:
        return None
    return COUNTRY_MSCI.get(country.strip())


def msci_tier_label(code: str) -> str:
    """Human-readable label for an MSCI tier code."""
    return MSCI_TIER_LABELS.get(code, code)
