"""The instrument model must reach equities through evidence-backed edges: a
commodity event traverses commodity -> sector -> the equity holdings, and debt
resolves to its issuer country. Empty exposure stays a real answer."""

from __future__ import annotations

from coruscant.common.config import CommodityConfig, CompanyConfig, DebtConfig, InstrumentsConfig
from coruscant.knowledge_graph.extraction import project_sector_edges, project_instrument_edges
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.queries import (
    commodity_exposure,
    debt_for_country,
    list_commodities,
    list_debt_instruments,
)


def _store() -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    # Real slugs so the GICS taxonomy resolves: Chevron→Energy, Sherwin→Materials.
    project_sector_edges(
        store,
        [
            CompanyConfig(slug="cvx", name="Chevron Corp", country="United States"),
            CompanyConfig(slug="shw", name="Sherwin-Williams Co", country="United States"),
        ],
    )
    instruments = InstrumentsConfig(
        commodities=[
            CommodityConfig(slug="crude-oil-wti", name="Crude Oil (WTI)", category="Energy", symbol="CL=F", affects_sectors=["Energy"]),
            CommodityConfig(slug="copper", name="Copper", category="Metals", symbol="HG=F", affects_sectors=["Materials"]),
        ],
        debt=[
            DebtConfig(slug="us-10y-treasury", name="US 10-Year Treasury", debt_type="sovereign", issuer_country="United States", symbol="^TNX"),
            DebtConfig(slug="india-10y-gsec", name="India 10-Year G-Sec", debt_type="sovereign", issuer_country="India"),
        ],
    )
    project_instrument_edges(store, instruments)
    return store


def test_commodity_exposure_reaches_equities_via_sector() -> None:
    store = _store()
    crude = commodity_exposure(store, "crude-oil-wti")
    assert crude.affects_sectors == ["Energy"]
    assert {h.key for h in crude.holdings} == {"cvx"}
    # Resolvable by display name too.
    assert commodity_exposure(store, "Copper").affects_sectors == ["Materials"]
    assert {h.key for h in commodity_exposure(store, "Copper").holdings} == {"shw"}
    # An unknown commodity is an honest empty answer.
    assert commodity_exposure(store, "uranium").holdings == []


def test_debt_resolves_to_issuer_country() -> None:
    store = _store()
    us = debt_for_country(store, "United States")
    assert [d.name for d in us] == ["US 10-Year Treasury"]
    assert us[0].debt_type == "sovereign" and us[0].symbol == "^TNX"
    assert [d.name for d in debt_for_country(store, "India")] == ["India 10-Year G-Sec"]
    assert debt_for_country(store, "Brazil") == []


def test_inventory_listings() -> None:
    store = _store()
    commodities = {c.name: c for c in list_commodities(store)}
    assert commodities["Crude Oil (WTI)"].category == "Energy"
    assert commodities["Crude Oil (WTI)"].affects_sectors == ["Energy"]
    assert commodities["Crude Oil (WTI)"].symbol == "CL=F"
    debt = {d.name for d in list_debt_instruments(store)}
    assert debt == {"US 10-Year Treasury", "India 10-Year G-Sec"}
