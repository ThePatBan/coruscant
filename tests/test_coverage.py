"""Whole-exchange coverage: the provider seam, CIK reconciliation (enrich, don't
duplicate; stable surrogate; GICS honesty), idempotency, and the resolve-rate proof.

Hermetic — the live SEC call is exercised only through an injected payload, never
the network."""

from __future__ import annotations

from coruscant.common.types import GraphNode
from coruscant.coverage.pipeline import ingest_coverage
from coruscant.coverage.provider import (
    IssuerAnchor,
    IssuerRecord,
    StaticCoverageProvider,
    UsEdgarCoverageProvider,
    is_real_exchange,
    normalize_cik,
    parse_company_tickers_exchange,
)
from coruscant.coverage.resolve import (
    Position,
    build_ticker_index,
    parse_brokerage_csv,
    resolve_positions,
)
from coruscant.exposure import queries as Q
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore

# The real SEC company_tickers_exchange.json envelope, in miniature: a keep, an
# OTC drop, a blank-exchange drop, and a real-exchange issuer with no ticker.
_SEC_PAYLOAD = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [
        [320193, "Apple Inc.", "AAPL", "Nasdaq"],
        [789019, "MICROSOFT CORP", "MSFT", "Nasdaq"],
        [1045810, "NVIDIA CORP", "NVDA", "Nasdaq"],
        [111, "Some OTC Shell", "SHEL", "OTC"],
        [222, "Blank Venue Co", "BVC", None],
        [333, "Fund Trust NoTicker", "", "NYSE"],
    ],
}


def _curated_apple(store: InMemoryKnowledgeGraphStore) -> None:
    """A curated Company node as ingestion writes it: ticker-keyed, unpadded CIK,
    authoritative GICS + source."""

    store.upsert_node(GraphNode(kind="Company", key="aapl", properties={
        "name": "Apple Inc.", "cik": "320193", "source": "tracked",
        "gics_sector": "Information Technology", "gics_code": "45202030"}))


# -- provider parse / filter ---------------------------------------------------

def test_normalize_cik_strips_padding() -> None:
    assert normalize_cik("0000320193") == "320193"
    assert normalize_cik(320193) == "320193"
    assert normalize_cik("  4962 ") == "4962"
    assert normalize_cik("") is None
    assert normalize_cik("not-a-cik") is None


def test_is_real_exchange_excludes_otc_and_blank() -> None:
    assert is_real_exchange("Nasdaq") and is_real_exchange("NYSE") and is_real_exchange("CBOE")
    assert is_real_exchange("NYSE American")  # a venue we don't hardcode still counts
    assert not is_real_exchange("OTC") and not is_real_exchange("") and not is_real_exchange(None)


def test_parse_filters_and_anchors() -> None:
    records, drops = parse_company_tickers_exchange(_SEC_PAYLOAD)
    assert [r.ticker for r in records] == ["AAPL", "MSFT", "NVDA", None]  # OTC + blank dropped
    assert drops["otc_or_blank_exchange"] == 2
    apple = records[0]
    assert apple.market == "US" and apple.exchange == "Nasdaq"
    assert apple.anchor("cik") == "320193" and apple.anchor("ticker") == "AAPL"
    assert apple.source == "sec-company-tickers"


def test_parse_malformed_payload_is_safe() -> None:
    assert parse_company_tickers_exchange({"fields": ["x"], "data": []}) == ([], {"malformed": 0})
    assert parse_company_tickers_exchange({"data": "nope"})[0] == []


def test_us_provider_offline_via_injected_payload() -> None:
    provider = UsEdgarCoverageProvider(payload=_SEC_PAYLOAD)
    assert provider.connected() and provider.market == "US"
    issuers = provider.list_issuers()
    assert len(issuers) == 4
    assert provider.last_drops["otc_or_blank_exchange"] == 2


# -- reconciliation: enrich, don't duplicate; stable surrogate; GICS honesty ----

def _ingest(store: InMemoryKnowledgeGraphStore, observed_at: str = "2026-07-01"):
    provider = UsEdgarCoverageProvider(payload=_SEC_PAYLOAD)
    return ingest_coverage(store, provider, observed_at=observed_at)


def test_cik_match_enriches_curated_node_without_duplicating() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    summary = _ingest(store)

    assert summary.enriched == 1 and summary.created == 3
    aapl = store.get_node("Company", "aapl")
    assert aapl is not None
    props = aapl.properties
    # Curated authority preserved:
    assert props["source"] == "tracked" and props["gics_sector"] == "Information Technology"
    assert "gics_status" not in props  # never labelled unresolved when curated GICS exists
    # Universe anchors added:
    assert props["ticker"] == "AAPL" and props["exchange"] == "Nasdaq"
    assert props["market"] == "US" and props["in_universe"] is True
    assert {"scheme": "cik", "value": "320193"} in props["anchors"]
    # No duplicate surrogate for Apple:
    assert store.get_node("Company", "us-320193") is None


def test_new_issuer_creates_stable_surrogate_with_unresolved_gics() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    _ingest(store)
    msft = store.get_node("Company", "us-789019")
    assert msft is not None
    props = msft.properties
    assert props["name"] == "MICROSOFT CORP" and props["cik"] == "789019"
    assert props["ticker"] == "MSFT" and props["exchange"] == "Nasdaq"
    assert props["source"] == "sec-company-tickers" and props["in_universe"] is True
    # Sector honesty: no curated GICS → labelled, never fabricated.
    assert props["gics_status"] == "unresolved"
    assert "gics_sector" not in props and "gics_code" not in props


def test_reconcile_is_idempotent_and_ids_are_stable() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    _ingest(store, "2026-07-01")
    keys_run1 = {n.key for n in store.nodes_of_kind("Company")}
    _ingest(store, "2026-07-02")  # re-run
    keys_run2 = {n.key for n in store.nodes_of_kind("Company")}
    assert keys_run1 == keys_run2 == {"aapl", "us-789019", "us-1045810", "us-333"}


def test_padded_cik_still_dedups_against_unpadded_curated() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)  # curated cik "320193"
    # An issuer whose feed CIK is zero-padded must still match the curated node.
    provider = StaticCoverageProvider("US", [IssuerRecord(
        market="US", name="APPLE INC", ticker="AAPL", exchange="Nasdaq",
        anchors=[IssuerAnchor(scheme="cik", value="0000320193")], source="sec-company-tickers")])
    summary = ingest_coverage(store, provider, observed_at="2026-07-01")
    assert summary.enriched == 1 and summary.created == 0
    assert store.get_node("Company", "us-320193") is None


def test_curated_ticker_is_not_clobbered_first_write_wins() -> None:
    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key="aapl", properties={
        "name": "Apple Inc.", "cik": "320193", "source": "tracked", "ticker": "AAPL.CURATED"}))
    _ingest(store)
    aapl = store.get_node("Company", "aapl")
    assert aapl is not None and aapl.properties["ticker"] == "AAPL.CURATED"


# -- coverage overview (honest, live off the graph) ----------------------------

def test_coverage_overview_counts_by_market_and_exchange() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    _ingest(store)
    ov = Q.coverage_overview(store)
    assert ov.connected and ov.total_companies == 4 and ov.in_universe == 4 and ov.curated == 0
    us = next(m for m in ov.by_market if m.market == "US")
    assert us.companies == 4 and us.in_universe == 4 and us.provider == "us-edgar"
    assert us.considered == 4 and us.excluded.get("otc_or_blank_exchange") == 2
    assert {(e.exchange, e.companies) for e in ov.by_exchange} == {("Nasdaq", 3), ("NYSE", 1)}


def test_coverage_overview_honest_empty_before_any_run() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    ov = Q.coverage_overview(store)
    assert ov.connected is False and ov.total_companies == 1


# -- resolve-rate: the proof a real book lands ---------------------------------

def test_resolve_positions_by_ticker_then_name() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    _ingest(store)
    book = [
        Position(ticker="AAPL"),                      # curated, by ticker
        Position(ticker="MSFT"),                      # surrogate, by ticker
        Position(ticker="ZZZZ"),                      # not covered → unresolved
        Position(name="Microsoft Corporation"),       # by org-name core match
    ]
    report = resolve_positions(store, book)
    assert report.total == 4 and report.resolved == 3
    assert report.by_ticker == 2 and report.by_name == 1 and report.unresolved == 1
    assert report.rate == 0.75
    by_ticker = build_ticker_index(store)
    assert by_ticker["AAPL"] == "aapl" and by_ticker["MSFT"] == "us-789019"


def test_resolve_ticker_punctuation_folds_dot_and_dash() -> None:
    store = InMemoryKnowledgeGraphStore()
    # SEC-style dash ticker on the node; a brokerage dot ticker must still resolve.
    store.upsert_node(GraphNode(kind="Company", key="us-1067983", properties={
        "name": "Berkshire Hathaway Inc", "ticker": "BRK-B", "in_universe": True, "market": "US"}))
    report = resolve_positions(store, [Position(ticker="BRK.B")])
    assert report.resolved == 1 and report.by_ticker == 1
    assert report.positions[0].company_key == "us-1067983"


def test_multi_class_tickers_one_cik_all_share_classes_resolve() -> None:
    """Alphabet lists GOOGL (Class A) and GOOG (Class C) as two rows under one CIK
    (1652044). The CIK dedups to a single node, but *both* tickers must resolve — a
    book holding either class is real. Losing the second class would be a fabricated
    'unresolved', the dishonest kind of gap."""

    store = InMemoryKnowledgeGraphStore()
    payload = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
            [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
        ],
    }
    summary = ingest_coverage(store, UsEdgarCoverageProvider(payload=payload), observed_at="2026-07-01")
    # One issuer node (CIK dedup), not two:
    assert summary.created == 1 and summary.enriched == 1
    nodes = store.nodes_of_kind("Company")
    assert len(nodes) == 1 and nodes[0].key == "us-1652044"
    # Both tickers survive as anchors (the primary property keeps the first-seen one):
    tickers = {a["value"] for a in nodes[0].properties["anchors"] if a["scheme"] == "ticker"}
    assert tickers == {"GOOGL", "GOOG"}
    # Every share class resolves to the single issuer node (dot-folding still works):
    report = resolve_positions(
        store, [Position(ticker="GOOGL"), Position(ticker="GOOG"), Position(ticker="GOOG.")]
    )
    assert report.resolved == 3 and report.by_ticker == 3
    assert {p.company_key for p in report.positions} == {"us-1652044"}
    idx = build_ticker_index(store)
    assert idx["GOOG"] == idx["GOOGL"] == "us-1652044"


def test_multi_class_ticker_anchors_are_stable_across_reruns() -> None:
    """Re-ingesting the same multi-class feed must not duplicate ticker anchors
    (idempotency extends to the multi-valued anchor path)."""

    store = InMemoryKnowledgeGraphStore()
    payload = {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [1652044, "Alphabet Inc.", "GOOGL", "Nasdaq"],
            [1652044, "Alphabet Inc.", "GOOG", "Nasdaq"],
        ],
    }
    provider = UsEdgarCoverageProvider(payload=payload)
    ingest_coverage(store, provider, observed_at="2026-07-01")
    ingest_coverage(store, provider, observed_at="2026-07-02")  # re-run
    node = store.get_node("Company", "us-1652044")
    assert node is not None
    ticker_anchors = [a for a in node.properties["anchors"] if a["scheme"] == "ticker"]
    assert [a["value"] for a in ticker_anchors] == ["GOOGL", "GOOG"]  # no duplicates


def test_curated_ticker_anchor_still_indexes_share_class() -> None:
    """A curated Apple node (ticker AAPL) enriched by the feed also gains any extra
    listed class as a ticker anchor, and that anchor resolves — without clobbering the
    curated primary ticker."""

    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    provider = StaticCoverageProvider("US", [
        IssuerRecord(market="US", name="Apple Inc.", ticker="AAPL", exchange="Nasdaq",
                     anchors=[IssuerAnchor(scheme="cik", value="320193"),
                              IssuerAnchor(scheme="ticker", value="AAPL")],
                     source="sec-company-tickers"),
        IssuerRecord(market="US", name="Apple Inc.", ticker="AAPL2", exchange="Nasdaq",
                     anchors=[IssuerAnchor(scheme="cik", value="320193"),
                              IssuerAnchor(scheme="ticker", value="AAPL2")],
                     source="sec-company-tickers"),
    ])
    ingest_coverage(store, provider, observed_at="2026-07-01")
    aapl = store.get_node("Company", "aapl")
    assert aapl is not None and aapl.properties["ticker"] == "AAPL"  # curated primary preserved
    report = resolve_positions(store, [Position(ticker="AAPL2")])
    assert report.resolved == 1 and report.positions[0].company_key == "aapl"


def test_empty_feed_is_an_honest_connected_run_not_a_crash() -> None:
    """A US feed that lists zero issuers (upstream outage returning an empty table)
    is an honest connected run: considered 0, universe empty, but ``connected`` true
    because we did reach and parse a feed — never a fabricated universe."""

    store = InMemoryKnowledgeGraphStore()
    provider = UsEdgarCoverageProvider(payload={"fields": ["cik", "name", "ticker", "exchange"], "data": []})
    summary = ingest_coverage(store, provider, observed_at="2026-07-01")
    assert summary.connected is True and summary.considered == 0
    assert summary.created == 0 and summary.enriched == 0 and summary.universe_total == 0
    ov = Q.coverage_overview(store)
    # A CoverageRun node exists, so the panel reports connected with an empty universe.
    assert ov.connected is True and ov.in_universe == 0


def test_coverage_overview_surfaces_last_run_deltas() -> None:
    store = InMemoryKnowledgeGraphStore()
    _curated_apple(store)
    _ingest(store)
    us = next(m for m in Q.coverage_overview(store).by_market if m.market == "US")
    assert us.created == 3 and us.enriched == 1


def test_parse_brokerage_csv_tolerates_column_naming() -> None:
    csv_text = "Symbol,Description,Quantity\nAAPL,Apple Inc,10\nMSFT,Microsoft Corp,5\nTotal,,15\n"
    positions = parse_brokerage_csv(csv_text)
    # The "Total" footer row has a symbol-ish value but is still parsed as a row;
    # what matters is the two real holdings resolve — validated end to end here.
    assert [p.ticker for p in positions][:2] == ["AAPL", "MSFT"]
    assert positions[0].name == "Apple Inc"


# -- wiring: runtime, CLI, API -------------------------------------------------

def test_run_coverage_offline_file_is_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from coruscant.apps.workspace_runtime import run_coverage
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import load_graph, save_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    seed = InMemoryKnowledgeGraphStore()
    _curated_apple(seed)
    save_graph(seed, settings.graph_snapshot_path)  # a curated node to enrich
    feed = tmp_path / "cte.json"
    feed.write_text(json.dumps(_SEC_PAYLOAD))

    summary = run_coverage(settings, market="us", file_path=feed)
    assert summary.enriched == 1 and summary.created == 3 and summary.universe_total == 4
    graph = load_graph(settings.graph_snapshot_path)
    assert graph.get_node("Company", "us-789019") is not None
    assert graph.get_node("Company", "us-320193") is None  # curated Apple not duplicated

    run_coverage(settings, market="us", file_path=feed)  # re-run
    assert len(load_graph(settings.graph_snapshot_path).nodes_of_kind("Company")) == 4


def test_run_coverage_rejects_unimplemented_market(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import pytest

    from coruscant.apps.workspace_runtime import run_coverage
    from coruscant.common.config import Settings

    settings = Settings(data_dir=tmp_path / "d", database_url="sqlite:///:memory:")
    with pytest.raises(ValueError, match="No coverage provider for market"):
        run_coverage(settings, market="jp")  # Japan not implemented; US + India are


def test_graph_coverage_endpoint() -> None:
    from fastapi.testclient import TestClient

    from coruscant.apps.api import create_app

    graph = InMemoryKnowledgeGraphStore()
    _curated_apple(graph)
    _ingest(graph)
    client = TestClient(create_app(graph_store=graph, require_auth=False))
    body = client.get("/graph/coverage").json()
    assert body["connected"] is True and body["in_universe"] == 4
    us = next(m for m in body["by_market"] if m["market"] == "US")
    assert us["provider"] == "us-edgar" and us["excluded"]["otc_or_blank_exchange"] == 2


def test_cli_coverage_parser_wires_command() -> None:
    from coruscant.apps import cli

    ns = cli.build_parser().parse_args(["coverage", "--market", "us", "--file", "x.json"])
    assert ns.func is cli.cmd_coverage and ns.market == "us" and ns.file == "x.json"


def test_cli_coverage_parser_wires_india_files() -> None:
    from coruscant.apps import cli

    ns = cli.build_parser().parse_args(
        ["coverage", "--market", "in", "--nse", "eq.csv", "--bse", "bse.csv",
         "--nifty", "n50.csv", "--sensex", "sx.csv"])
    assert ns.market == "in" and ns.nse == "eq.csv" and ns.bse == "bse.csv"
    assert ns.nifty == "n50.csv" and ns.sensex == "sx.csv"


def test_cli_coverage_parser_wires_uk_files() -> None:
    from coruscant.apps import cli

    ns = cli.build_parser().parse_args(
        ["coverage", "--market", "gb", "--lse", "lse.csv",
         "--ftse100", "f100.csv", "--ftse250", "f250.csv"])
    assert ns.market == "gb" and ns.lse == "lse.csv"
    assert ns.ftse100 == "f100.csv" and ns.ftse250 == "f250.csv"


# == India: NSE + BSE, ISIN-unified; Nifty/Sensex index membership ==============
#
# Fixtures mirror the real files in miniature: NSE keeps EQ/BE + drops a bond and a
# blank-ISIN row; BSE is active-equity + drops a suspended scrip; RELIANCE/TCS are
# dual-listed (same ISIN on both exchanges), INFY is NSE-only, ABB is BSE-only.
_NSE_EQUITY = (
    "SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
    "INFY, Infosys Limited, EQ, 1995-06-08, 5, 1, INE009A01021, 5\n"
    "RELIANCE, Reliance Industries Limited, EQ, 1995-11-29, 10, 1, INE002A01018, 10\n"
    "TCS, Tata Consultancy Services Limited, EQ, 2004-08-25, 1, 1, INE467B01029, 1\n"
    "GILT, Some Gilt Bond, N2, 2020-01-01, 100, 1, INE999Z01011, 100\n"     # non-equity series → drop
    "NOISIN, No Isin Co, EQ, 2020-01-01, 10, 1, , 10\n"                     # blank ISIN → drop
)
_BSE_SCRIP = (
    "Security Code,Security Id,Security Name,Status,Group,Face Value,ISIN No,Industry,Instrument\n"
    "500325,RELIANCE,RELIANCE INDUSTRIES LTD,Active,A,10,INE002A01018,Refineries,Equity\n"
    "532540,TCS,TATA CONSULTANCY SERVICES LTD,Active,A,1,INE467B01029,IT - Software,Equity\n"
    "500002,ABB,ABB INDIA LIMITED,Active,A,2,INE117A01022,Capital Goods,Equity\n"
    "590099,SUSP,Suspended Co,Suspended,X,10,INE888A01011,Misc,Equity\n"    # suspended → drop
)
_NIFTY50 = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Infosys Ltd.,Information Technology,INFY,EQ,INE009A01021\n"
    "Reliance Industries Ltd.,Oil Gas,RELIANCE,EQ,INE002A01018\n"
    "Tata Consultancy Services Ltd.,Information Technology,TCS,EQ,INE467B01029\n"
)
_SENSEX = (
    "Security Code,Security Id,Security Name,ISIN No\n"
    "500325,RELIANCE,RELIANCE INDUSTRIES LTD,INE002A01018\n"
    "532540,TCS,TATA CONSULTANCY SERVICES LTD,INE467B01029\n"
)


def _india_provider():  # type: ignore[no-untyped-def]
    from coruscant.coverage.provider import IndiaCoverageProvider

    return IndiaCoverageProvider(
        nse_text=_NSE_EQUITY, bse_text=_BSE_SCRIP, nifty_text=_NIFTY50, sensex_text=_SENSEX)


def test_parse_nse_equity_filters_series_and_blank_isin() -> None:
    from coruscant.coverage.provider import parse_nse_equity_list

    rows, drops = parse_nse_equity_list(_NSE_EQUITY)
    assert [r["symbol"] for r in rows] == ["INFY", "RELIANCE", "TCS"]
    assert drops["nse_non_equity_series"] == 1 and drops["nse_blank_isin"] == 1
    assert rows[0]["isin"] == "INE009A01021" and rows[0]["name"] == "Infosys Limited"


def test_parse_bse_scrip_filters_suspended_and_keeps_equity() -> None:
    from coruscant.coverage.provider import parse_bse_scrip_list

    rows, drops = parse_bse_scrip_list(_BSE_SCRIP)
    assert {r["security_id"] for r in rows} == {"RELIANCE", "TCS", "ABB"}
    assert drops["bse_inactive"] == 1
    abb = next(r for r in rows if r["security_id"] == "ABB")
    assert abb["code"] == "500002" and abb["isin"] == "INE117A01022"


def test_parse_bse_scrip_accepts_live_json_api() -> None:
    from coruscant.coverage.provider import parse_bse_scrip_list

    # The live BSE ListofScripData API returns JSON with keys SCRIP_CD/scrip_id/
    # ISIN_NUMBER/Issuer_Name/Segment — parsed the same as the CSV export.
    api = (
        '[{"SCRIP_CD":"500325","scrip_id":"RELIANCE","Issuer_Name":"Reliance Industries Limited",'
        '"Status":"Active","ISIN_NUMBER":"INE002A01018","Segment":"Equity"},'
        '{"SCRIP_CD":"590099","scrip_id":"SUSP","Issuer_Name":"Suspended Co",'
        '"Status":"Suspended","ISIN_NUMBER":"INE888A01011","Segment":"Equity"}]'
    )
    rows, drops = parse_bse_scrip_list(api)
    assert [r["security_id"] for r in rows] == ["RELIANCE"]
    assert rows[0]["code"] == "500325" and rows[0]["isin"] == "INE002A01018"
    assert drops["bse_inactive"] == 1


def test_parse_bse_empty_is_not_malformed() -> None:
    from coruscant.coverage.provider import parse_bse_scrip_list

    # An NSE-only run supplies no BSE text — that is legitimate, not a malformed drop.
    assert parse_bse_scrip_list("") == ([], {})


def test_unify_by_isin_dual_listing_and_anchors() -> None:
    from coruscant.coverage.provider import (
        parse_bse_scrip_list,
        parse_nse_equity_list,
        unify_india_issuers,
    )

    nse, _ = parse_nse_equity_list(_NSE_EQUITY)
    bse, _ = parse_bse_scrip_list(_BSE_SCRIP)
    records, stats = unify_india_issuers(nse, bse)
    by_isin = {r.anchor("isin"): r for r in records}
    # One node per ISIN: NSE∩BSE collapsed (RELIANCE/TCS), NSE-only + BSE-only kept.
    assert set(by_isin) == {"INE009A01021", "INE002A01018", "INE467B01029", "INE117A01022"}
    assert stats == {"nse_only": 1, "bse_only": 1, "dual_listed": 2}
    reliance = by_isin["INE002A01018"]
    assert reliance.exchange == "NSE & BSE" and reliance.ticker == "RELIANCE"
    assert reliance.anchor("ticker") == "RELIANCE" and reliance.anchor("bse_code") == "500325"
    # BSE-only issuer resolves via its BSE Security Id as the ticker.
    abb = by_isin["INE117A01022"]
    assert abb.exchange == "BSE" and abb.ticker == "ABB"
    # NSE-only issuer has no bse_code anchor.
    assert by_isin["INE009A01021"].exchange == "NSE"
    assert by_isin["INE009A01021"].anchor("bse_code") is None


def test_india_provider_offline_and_drops() -> None:
    provider = _india_provider()
    assert provider.connected() and provider.market == "IN"
    issuers = provider.list_issuers()
    assert len(issuers) == 4
    assert provider.last_drops["nse_non_equity_series"] == 1
    assert provider.last_drops["bse_inactive"] == 1
    # Stats are NOT drops — the overlap is reported via by_exchange, not `excluded`.
    assert "dual_listed" not in provider.last_drops


def test_india_ingest_creates_isin_nodes_gics_unresolved_and_indices() -> None:
    from coruscant.coverage.pipeline import CONSTITUENT_OF, INDEX_KIND, ingest_coverage

    store = InMemoryKnowledgeGraphStore()
    summary = ingest_coverage(store, _india_provider(), observed_at="2026-07-01")
    assert summary.market == "IN" and summary.created == 4 and summary.enriched == 0
    assert summary.by_exchange == {"NSE": 1, "NSE & BSE": 2, "BSE": 1}
    assert summary.indices == {"Nifty 50": 3, "BSE Sensex": 2}

    infy = store.get_node("Company", "in-INE009A01021")
    assert infy is not None
    assert infy.properties["ticker"] == "INFY" and infy.properties["exchange"] == "NSE"
    assert infy.properties["market"] == "IN" and infy.properties["in_universe"] is True
    # Sector honesty: India ≈ MSCI EM, but no fabricated per-company GICS/tier.
    assert infy.properties["gics_status"] == "unresolved"
    assert "gics_sector" not in infy.properties

    # Index nodes + constituent_of edges (Company → Index), provenance-backed.
    indices = {n.key: n.properties for n in store.nodes_of_kind(INDEX_KIND)}
    assert indices["nifty-50"]["name"] == "Nifty 50" and indices["nifty-50"]["constituents"] == 3
    edges = {(e.source_key, e.target_key) for e in store.edges_by_relation(CONSTITUENT_OF)}
    assert ("in-INE009A01021", "nifty-50") in edges
    assert ("in-INE002A01018", "bse-sensex") in edges
    nifty_edge = next(e for e in store.edges_by_relation(CONSTITUENT_OF) if e.target_key == "nifty-50")
    assert nifty_edge.properties["source"] == "nse-indices"  # every edge cites its source


def test_india_reingest_is_idempotent_nodes_and_edges_stable() -> None:
    from coruscant.coverage.pipeline import CONSTITUENT_OF, ingest_coverage

    store = InMemoryKnowledgeGraphStore()
    ingest_coverage(store, _india_provider(), observed_at="2026-07-01")
    keys1 = {n.key for n in store.nodes_of_kind("Company")}
    edges1 = len(store.edges_by_relation(CONSTITUENT_OF))
    ingest_coverage(store, _india_provider(), observed_at="2026-07-02")  # re-run
    keys2 = {n.key for n in store.nodes_of_kind("Company")}
    edges2 = len(store.edges_by_relation(CONSTITUENT_OF))
    assert keys1 == keys2 and edges1 == edges2 == 5


def test_india_domestic_not_merged_with_us_adr() -> None:
    """The curated Infosys ADR (US-listed, slug-keyed, US ADR ISIN) must NOT merge
    with the domestic NSE listing (INE009A01021). Exact-ISIN dedup won't touch it;
    ADR↔domestic reconciliation is a separate GLEIF-LEI step, never a coverage merge."""

    from coruscant.coverage.pipeline import ingest_coverage

    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key="infosys", properties={
        "name": "Infosys Limited", "source": "tracked", "ticker": "INFY",
        "anchors": [{"scheme": "isin", "value": "US4567881085"}]}))  # US ADR ISIN, not domestic
    ingest_coverage(store, _india_provider(), observed_at="2026-07-01")
    # Both identities survive, distinct:
    assert store.get_node("Company", "infosys") is not None
    domestic = store.get_node("Company", "in-INE009A01021")
    assert domestic is not None and domestic.properties["ticker"] == "INFY"


def test_index_constituent_outside_universe_is_counted_not_fabricated() -> None:
    from coruscant.coverage.pipeline import CONSTITUENT_OF, INDEX_KIND, ingest_coverage
    from coruscant.coverage.provider import IndiaCoverageProvider

    # A Nifty list naming a symbol/ISIN absent from the NSE/BSE universe: the
    # constituent is counted unresolved, never linked to a fabricated node.
    nifty = _NIFTY50 + "Ghost Corp,Misc,GHOST,EQ,INE000X01099\n"
    provider = IndiaCoverageProvider(nse_text=_NSE_EQUITY, bse_text=_BSE_SCRIP, nifty_text=nifty)
    store = InMemoryKnowledgeGraphStore()
    ingest_coverage(store, provider, observed_at="2026-07-01")
    nifty_node = store.get_node(INDEX_KIND, "nifty-50")
    assert nifty_node is not None
    assert nifty_node.properties["constituents"] == 3
    assert nifty_node.properties["constituents_unresolved"] == 1
    ghosts = [e for e in store.edges_by_relation(CONSTITUENT_OF) if "GHOST" in e.source_key]
    assert ghosts == []  # no fabricated edge


def test_resolve_indian_book_by_symbol_and_isin() -> None:
    from coruscant.coverage.pipeline import ingest_coverage
    from coruscant.coverage.resolve import build_isin_index, parse_brokerage_csv, resolve_positions

    store = InMemoryKnowledgeGraphStore()
    ingest_coverage(store, _india_provider(), observed_at="2026-07-01")
    # A Zerodha-style export: trading symbol + ISIN columns.
    csv_text = (
        "tradingsymbol,isin,quantity\n"
        "INFY,INE009A01021,10\n"       # symbol hit (ticker wins before ISIN)
        ",INE002A01018,5\n"            # ISIN-only hit (Reliance)
        "ABB,,3\n"                     # BSE-only symbol hit
        "ZZZZ,IN0000000000,1\n"        # neither → unresolved
    )
    report = resolve_positions(store, parse_brokerage_csv(csv_text))
    assert report.total == 4 and report.resolved == 3
    assert report.by_ticker == 2 and report.by_isin == 1 and report.unresolved == 1
    assert build_isin_index(store)["INE002A01018"] == "in-INE002A01018"


def test_run_coverage_india_offline_files_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.workspace_runtime import run_coverage
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import load_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    nse = tmp_path / "eq.csv"
    nse.write_text(_NSE_EQUITY)
    bse = tmp_path / "bse.csv"
    bse.write_text(_BSE_SCRIP)
    nifty = tmp_path / "n50.csv"
    nifty.write_text(_NIFTY50)

    summary = run_coverage(
        settings, market="in", sources={"nse": nse, "bse": bse, "nifty": nifty})
    assert summary.created == 4 and summary.universe_total == 4
    assert summary.indices == {"Nifty 50": 3}
    graph = load_graph(settings.graph_snapshot_path)
    assert graph.get_node("Company", "in-INE009A01021") is not None

    run_coverage(settings, market="in", sources={"nse": nse, "bse": bse, "nifty": nifty})  # re-run
    assert len(load_graph(settings.graph_snapshot_path).nodes_of_kind("Company")) == 4


# == UK: London Stock Exchange, ISIN-identified; FTSE 100/250 index membership ==
#
# Fixtures mirror the LSE "List of all companies" in miniature: Main Market + AIM
# rows, a SEDOL + Companies House number as extra anchors, and a blank-ISIN drop.
_LSE_LIST = (
    "Company,TIDM,ISIN,SEDOL,Company Number,Market,ICB Industry,Country of Incorporation\n"
    "BP p.l.c.,BP,GB0007980591,0798059,00102498,Main Market,Energy,United Kingdom\n"
    "HSBC Holdings plc,HSBA,GB0005405286,0540528,00617987,Main Market,Financials,United Kingdom\n"
    "Vodafone Group plc,VOD,GB00BH4HKS39,BH4HKS3,03371853,Main Market,Telecommunications,United Kingdom\n"
    "boohoo group plc,BOO,JE00BG6L7297,BG6L729,,AIM,Consumer Discretionary,Jersey\n"
    "Blank Co,BLNK,,,,Main Market,Misc,United Kingdom\n"           # blank ISIN → drop
)
_FTSE100 = (
    "Company,EPIC,ISIN\n"
    "BP p.l.c.,BP,GB0007980591\n"
    "HSBC Holdings plc,HSBA,GB0005405286\n"
    "Vodafone Group plc,VOD,GB00BH4HKS39\n"
)


def _uk_provider():  # type: ignore[no-untyped-def]
    from coruscant.coverage.provider import UkLseCoverageProvider

    return UkLseCoverageProvider(lse_text=_LSE_LIST, ftse100_text=_FTSE100)


def test_parse_lse_list_anchors_and_segment_and_blank_isin() -> None:
    from coruscant.coverage.provider import parse_lse_company_list

    records, drops = parse_lse_company_list(_LSE_LIST)
    assert [r.ticker for r in records] == ["BP", "HSBA", "VOD", "BOO"]  # blank-ISIN row dropped
    assert drops["gb_blank_isin"] == 1
    bp = records[0]
    assert bp.market == "GB" and bp.exchange == "LSE Main Market"
    assert bp.anchor("isin") == "GB0007980591" and bp.anchor("ticker") == "BP"
    assert bp.anchor("sedol") == "0798059" and bp.anchor("company_number") == "00102498"
    boo = records[3]
    assert boo.exchange == "LSE AIM"  # segment mapping
    assert boo.anchor("company_number") is None  # absent column value → no fabricated anchor


def test_uk_ingest_creates_isin_nodes_gics_unresolved_and_ftse_index() -> None:
    from coruscant.coverage.pipeline import CONSTITUENT_OF, INDEX_KIND, ingest_coverage

    store = InMemoryKnowledgeGraphStore()
    summary = ingest_coverage(store, _uk_provider(), observed_at="2026-07-01")
    assert summary.market == "GB" and summary.created == 4
    assert summary.by_exchange == {"LSE Main Market": 3, "LSE AIM": 1}
    assert summary.indices == {"FTSE 100": 3}

    bp = store.get_node("Company", "gb-GB0007980591")
    assert bp is not None
    assert bp.properties["ticker"] == "BP" and bp.properties["exchange"] == "LSE Main Market"
    assert bp.properties["market"] == "GB" and bp.properties["gics_status"] == "unresolved"
    schemes = {a["scheme"] for a in bp.properties["anchors"]}
    assert schemes == {"isin", "ticker", "sedol", "company_number"}

    ftse = store.get_node(INDEX_KIND, "ftse-100")
    assert ftse is not None and ftse.properties["constituents"] == 3
    edges = {(e.source_key, e.target_key) for e in store.edges_by_relation(CONSTITUENT_OF)}
    assert ("gb-GB0007980591", "ftse-100") in edges


def test_uk_reingest_is_idempotent() -> None:
    from coruscant.coverage.pipeline import ingest_coverage

    store = InMemoryKnowledgeGraphStore()
    ingest_coverage(store, _uk_provider(), observed_at="2026-07-01")
    keys1 = {n.key for n in store.nodes_of_kind("Company")}
    ingest_coverage(store, _uk_provider(), observed_at="2026-07-02")  # re-run
    assert keys1 == {n.key for n in store.nodes_of_kind("Company")}


def test_uk_domestic_not_merged_with_us_adr() -> None:
    """The curated BP ADR (US-listed, slug 'bp', US ADR ISIN) must NOT merge with the
    domestic LSE listing (GB0007980591). Exact-ISIN dedup won't touch it."""

    from coruscant.coverage.pipeline import ingest_coverage

    store = InMemoryKnowledgeGraphStore()
    store.upsert_node(GraphNode(kind="Company", key="bp", properties={
        "name": "BP p.l.c.", "source": "tracked", "ticker": "BP",
        "anchors": [{"scheme": "isin", "value": "US0556221044"}]}))  # US ADR ISIN, not GB
    ingest_coverage(store, _uk_provider(), observed_at="2026-07-01")
    assert store.get_node("Company", "bp") is not None
    domestic = store.get_node("Company", "gb-GB0007980591")
    assert domestic is not None and domestic.properties["ticker"] == "BP"


def test_resolve_uk_book_by_ticker_isin_and_sedol() -> None:
    from coruscant.coverage.pipeline import ingest_coverage
    from coruscant.coverage.resolve import build_sedol_index, parse_brokerage_csv, resolve_positions

    store = InMemoryKnowledgeGraphStore()
    ingest_coverage(store, _uk_provider(), observed_at="2026-07-01")
    # A Hargreaves-Lansdown-style export: TIDM + SEDOL + ISIN columns.
    csv_text = (
        "TIDM,SEDOL,ISIN,Quantity\n"
        "BP,,,100\n"                    # ticker hit
        ",0540528,,50\n"               # SEDOL-only hit (HSBC)
        ",,GB00BH4HKS39,25\n"          # ISIN-only hit (Vodafone)
        "ZZZ,,,1\n"                    # miss
    )
    report = resolve_positions(store, parse_brokerage_csv(csv_text))
    assert report.total == 4 and report.resolved == 3
    assert report.by_ticker == 1 and report.by_sedol == 1 and report.by_isin == 1
    assert report.unresolved == 1
    assert build_sedol_index(store)["0540528"] == "gb-GB0005405286"


def test_run_coverage_uk_offline_files_idempotent_and_market_alias(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from coruscant.apps.workspace_runtime import run_coverage
    from coruscant.common.config import Settings
    from coruscant.knowledge_graph.persistence import load_graph

    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, database_url=f"sqlite:///{data_dir / 'c.db'}")
    lse = tmp_path / "lse.csv"
    lse.write_text(_LSE_LIST)
    ftse = tmp_path / "ftse100.csv"
    ftse.write_text(_FTSE100)

    # "uk" is accepted as an alias for the GB market.
    summary = run_coverage(settings, market="uk", sources={"lse": lse, "ftse100": ftse})
    assert summary.market == "GB" and summary.created == 4 and summary.indices == {"FTSE 100": 3}
    graph = load_graph(settings.graph_snapshot_path)
    assert graph.get_node("Company", "gb-GB0007980591") is not None

    run_coverage(settings, market="gb", sources={"lse": lse, "ftse100": ftse})  # re-run, "gb" form
    assert len(load_graph(settings.graph_snapshot_path).nodes_of_kind("Company")) == 4
