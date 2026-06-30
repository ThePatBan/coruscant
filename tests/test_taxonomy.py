"""The curated GICS / MSCI taxonomy is reference data, so its invariants are
worth pinning: every classification is well-formed, the 8-digit codes are
internally consistent with the hierarchy they encode, and the map stays in sync
with the tracked-company config (a new company without a GICS code should be a
loud test failure, not a silent SIC fallback in production)."""

from __future__ import annotations

from pathlib import Path

from coruscant.common.config import load_companies
from coruscant.knowledge_graph.taxonomy import (
    COMPANY_GICS_CODE,
    COUNTRY_MSCI,
    GICS_SECTORS,
    GICS_SUB_INDUSTRIES,
    MSCI_TIER_LABELS,
    company_gics,
    country_msci_tier,
)

_CONFIG_DIR = Path(__file__).resolve().parents[1] / "deploy" / "dow-config"


def test_every_gics_node_is_well_formed() -> None:
    for code, node in GICS_SUB_INDUSTRIES.items():
        assert node.code == code, f"{code}: code field mismatch ({node.code})"
        assert len(code) == 8 and code.isdigit(), f"{code}: not an 8-digit GICS code"
        assert node.sector in GICS_SECTORS, f"{code}: {node.sector!r} is not a GICS sector"
        assert node.industry_group and node.industry and node.sub_industry, f"{code}: missing a level name"


def test_codes_are_internally_consistent_with_the_hierarchy() -> None:
    """The 8-digit code IS the hierarchy: rows sharing a level name must share the
    code prefix for that level, and no two sub-industries may share a code."""
    by_sector: dict[str, set[str]] = {}
    by_group: dict[tuple[str, str], set[str]] = {}
    by_industry: dict[tuple[str, str, str], set[str]] = {}
    for node in GICS_SUB_INDUSTRIES.values():
        by_sector.setdefault(node.sector, set()).add(node.code[:2])
        by_group.setdefault((node.sector, node.industry_group), set()).add(node.code[:4])
        by_industry.setdefault((node.sector, node.industry_group, node.industry), set()).add(node.code[:6])
    for sector, prefixes in by_sector.items():
        assert len(prefixes) == 1, f"sector {sector!r} maps to multiple 2-digit codes: {prefixes}"
    for group, prefixes in by_group.items():
        assert len(prefixes) == 1, f"industry group {group} maps to multiple 4-digit codes: {prefixes}"
    for industry, prefixes in by_industry.items():
        assert len(prefixes) == 1, f"industry {industry} maps to multiple 6-digit codes: {prefixes}"


def test_every_country_tier_is_valid() -> None:
    for country, tier in COUNTRY_MSCI.items():
        assert tier in MSCI_TIER_LABELS, f"{country}: {tier!r} is not an MSCI tier"


def test_curated_map_covers_every_tracked_company() -> None:
    companies = load_companies(_CONFIG_DIR)
    missing_gics = sorted(c.slug for c in companies if company_gics(c.slug) is None)
    missing_tier = sorted(c.slug for c in companies if country_msci_tier(c.country) is None)
    assert not missing_gics, f"companies missing a GICS classification: {missing_gics}"
    assert not missing_tier, f"companies missing an MSCI tier (check country): {missing_tier}"
    # Every code referenced by a company must resolve to a registered node.
    unresolved = sorted(s for s, code in COMPANY_GICS_CODE.items() if code not in GICS_SUB_INDUSTRIES)
    assert not unresolved, f"companies pointing at an unregistered GICS code: {unresolved}"


def test_known_post_2023_reclassifications() -> None:
    # Visa moved Information Technology -> Financials in the March-2023 GICS revision;
    # Amazon is Consumer Discretionary; Disney is Communication Services. Guardrails.
    assert company_gics("v").sector == "Financials"
    assert company_gics("v").sub_industry == "Transaction & Payment Processing Services"
    assert company_gics("amzn").sector == "Consumer Discretionary"
    assert company_gics("dis").sector == "Communication Services"
    assert company_gics("nvda").sub_industry == "Semiconductors"
