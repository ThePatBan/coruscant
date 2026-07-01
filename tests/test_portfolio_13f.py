"""13F portfolio front door: parse the info table, resolve holdings, project edges."""

from __future__ import annotations

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph import queries as Q
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.substrate import AccessTier
from coruscant.portfolio.holdings import HOLDS, FUND_KIND, ingest_fund_holdings
from coruscant.portfolio.thirteenf import FundFiling, FundHolding, parse_13f_info_table

# A realistic 13F information table: namespaced, two share classes of one issuer +
# an out-of-coverage position.
_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip><value>75000000</value>
    <shrsOrPrnAmt><sshPrnamt>300000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>NOTE 0.000 11/15/2025</titleOfClass>
    <cusip>037833100</cusip><value>5000000</value>
    <shrsOrPrnAmt><sshPrnamt>5000000</sshPrnamt><sshPrnamtType>PRN</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>SOME PRIVATE HOLDINGS LLC</nameOfIssuer><titleOfClass>COM</titleOfClass>
    <cusip>999999999</cusip><value>1234</value>
    <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


def test_parse_13f_info_table() -> None:
    holdings = parse_13f_info_table(_XML)
    assert len(holdings) == 3
    apple = holdings[0]
    assert apple.issuer == "APPLE INC" and apple.cusip == "037833100"
    assert apple.value == 75000000 and apple.shares == 300000000


def _store_with_company(name: str, key: str) -> InMemoryKnowledgeGraphStore:
    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key=key, properties={"name": name}))
    return store


def test_ingest_resolves_aggregates_and_counts_out_of_coverage() -> None:
    store = _store_with_company("Apple", "apple")  # our SEC-conformed label
    filing = FundFiling(cik="1067983", name="Berkshire Hathaway Inc", period="2024-12-31",
                        source_url="https://sec.gov/x", holdings=parse_13f_info_table(_XML))

    summary = ingest_fund_holdings(store, filing, observed_at="2026-07-01")
    assert summary.positions == 3
    assert summary.resolved == 1  # one covered company (Apple)
    assert summary.out_of_coverage == 1  # the private LLC line (the 2 Apple lines both resolve)

    edges = [e for e in store.outgoing(FUND_KIND, "fund-1067983") if e.relation == HOLDS]
    assert len(edges) == 1  # two Apple share classes aggregated into one holds edge
    props = edges[0].properties
    assert props["value"] == 80000000 and props["shares"] == 305000000  # summed across classes
    assert props["cusip"] == "037833100" and props["access_tier"] == "public"
    assert props["valid_from"] == "2024-12-31"  # bitemporal from the 13F period
    fund = store.get_node(FUND_KIND, "fund-1067983")
    assert fund is not None and fund.properties["positions"] == 3


def test_holding_does_not_attribute_to_a_lookalike() -> None:
    # A fund holding "APPLE FORD INC" must not attach to our "Apple" node.
    store = _store_with_company("Apple", "apple")
    filing = FundFiling(cik="1", name="Test Fund",
                        holdings=[FundHolding(issuer="Apple Ford Inc", value=1, shares=1)])
    assert ingest_fund_holdings(store, filing, observed_at="2026-07-01").resolved == 0


def test_fund_holdings_query_tier_asof_and_sorting() -> None:
    store = _store_with_company("Apple", "apple")
    store.upsert_node(GraphNode(kind="Company", key="chevron", properties={"name": "Chevron Corp"}))
    filing = FundFiling(cik="1067983", name="Berkshire Hathaway Inc", period="2024-12-31",
                        holdings=[FundHolding(issuer="APPLE INC", value=75, shares=300),
                                  FundHolding(issuer="CHEVRON CORP", value=180, shares=120)])
    ingest_fund_holdings(store, filing, observed_at="2026-07-01")

    assert [f.key for f in Q.list_funds(store)] == ["fund-1067983"]
    view = Q.fund_holdings(store, "fund-1067983", clearance=AccessTier.PUBLIC)
    assert view is not None
    assert [h.company.key for h in view.holdings] == ["chevron", "apple"]  # by value, desc
    assert view.fund.resolved == 2
    # Bitemporal: before the report period, the holdings do not yet apply.
    earlier = Q.fund_holdings(store, "fund-1067983", as_of="2020-01-01")
    assert earlier is not None and earlier.holdings == []
    assert Q.fund_holdings(store, "missing") is None


def _exposure_store() -> InMemoryKnowledgeGraphStore:
    from coruscant.common.types import GraphEdge
    store = _store_with_company("Apple", "apple")
    store.upsert_node(GraphNode(kind="Company", key="chevron", properties={"name": "Chevron Corp"}))
    store.upsert_edge(GraphEdge(source_kind="Company", source_key="apple", relation="in_sector",
                               target_kind="Industry", target_key="it",
                               properties={"sector": "Information Technology"}))
    store.upsert_edge(GraphEdge(source_kind="Company", source_key="chevron", relation="in_sector",
                               target_kind="Industry", target_key="energy",
                               properties={"sector": "Energy"}))
    filing = FundFiling(cik="1067983", name="Berkshire Hathaway Inc", period="2024-12-31",
                        holdings=[FundHolding(issuer="APPLE INC", value=75, shares=300),
                                  FundHolding(issuer="CHEVRON CORP", value=180, shares=120)])
    ingest_fund_holdings(store, filing, observed_at="2026-07-01")
    return store


def test_portfolio_exposure_scopes_event_to_the_fund() -> None:
    store = _exposure_store()
    # An Energy event touches only the fund's Chevron holding, with its value.
    energy = Q.portfolio_exposure(store, "fund-1067983", pathway="sector", term="Energy")
    assert energy is not None
    assert [h.company.key for h in energy.exposed] == ["chevron"]
    assert energy.exposed_value == 180 and energy.total_value == 255
    # A sector the book doesn't touch is a real, empty answer.
    assert Q.portfolio_exposure(store, "fund-1067983", pathway="sector", term="Utilities").exposed == []  # type: ignore[union-attr]
    assert Q.portfolio_exposure(store, "missing", pathway="sector", term="Energy") is None


def test_portfolio_profile_is_value_weighted() -> None:
    profile = Q.portfolio_profile(_exposure_store(), "fund-1067983")
    assert profile is not None and profile.total_value == 255
    by_sector = {b.label: b.value for b in profile.by_sector}
    assert by_sector == {"Energy": 180, "Information Technology": 75}
