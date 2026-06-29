"""Coruscant command line interface.

Subcommands cover the operational surface of the MVP: inspect configuration,
run the ingestion lifecycle, query the corpus with evidence, explore the graph,
and serve the API.
"""

from __future__ import annotations

import argparse

from coruscant.apps.runtime import (
    build_schedule_store,
    due_source_types,
    load_engine,
    load_graph_store,
    run_ingestion,
    seed_demo_user,
)
from coruscant.common.config import get_settings, load_companies
from coruscant.common.logging import configure_logging
from coruscant.ingestion.registry import default_registry
from coruscant.search.reference import TemplateReasoningLayer


def cmd_companies(_: argparse.Namespace) -> int:
    settings = get_settings()
    for company in load_companies(settings.config_dir):
        industry = company.industry or "-"
        print(f"{company.slug:12} {company.name:24} {industry}")
    return 0


def cmd_sources(_: argparse.Namespace) -> int:
    for definition in default_registry().definitions():
        print(f"{definition.source_type:20} {definition.label:28} -> {definition.document_type}")
    return 0


def cmd_ingest(_: argparse.Namespace) -> int:
    configure_logging()
    report = run_ingestion()
    print(
        f"Ingested {report.document_count} documents across "
        f"{len(report.companies)} companies and {len(report.source_types)} sources."
    )
    for source_type in report.source_types:
        count = sum(1 for item in report.items if item.source_type == source_type)
        print(f"  {source_type:20} {count}")
    print(
        f"Intelligence: {report.summary_count} summaries, {report.event_count} events, "
        f"{report.material_change_count} material change sets."
    )
    if seed_demo_user():
        settings = get_settings()
        print(f"Seeded demo user: {settings.demo_email} / {settings.demo_password}")
    if report.errors:
        print(f"Errors: {len(report.errors)}")
        for error in report.errors:
            print(f"  ! {error}")
    return 0


def cmd_schedule(_: argparse.Namespace) -> int:
    settings = get_settings()
    last = build_schedule_store(settings).last_runs()
    due = set(due_source_types(settings))
    for definition in default_registry().definitions():
        marker = "DUE" if definition.source_type in due else "ok "
        last_run = last.get(definition.source_type, "never")
        print(f"  [{marker}] {definition.source_type:20} cadence={definition.cadence_days}d  last={last_run}")
    print(f"{len(due)} source(s) due for ingestion.")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    engine = load_engine()
    if len(engine) == 0:
        print("Corpus is empty. Run `coruscant ingest` first.")
        return 1
    reasoning = TemplateReasoningLayer(engine)
    print(reasoning.answer(args.query))
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    graph = load_graph_store()
    node = graph.get_node("Company", args.company)
    if node is None:
        print(f"No graph node for company '{args.company}'. Run `coruscant ingest` first.")
        return 1
    print(f"Company: {args.company}")
    for edge, target in graph.neighbors("Company", args.company):
        title = target.properties.get("title") if target is not None else None
        suffix = f" ({title})" if title else ""
        print(f"  -{edge.relation}-> {edge.target_kind}:{edge.target_key}{suffix}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("coruscant.apps.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coruscant", description="Coruscant intelligence platform")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("companies", help="List configured companies").set_defaults(func=cmd_companies)
    sub.add_parser("sources", help="List registered ingestion sources").set_defaults(func=cmd_sources)
    sub.add_parser("ingest", help="Run the full ingestion lifecycle").set_defaults(func=cmd_ingest)
    sub.add_parser("schedule", help="Show which sources are due for ingestion").set_defaults(func=cmd_schedule)

    query = sub.add_parser("query", help="Answer a query against the ingested corpus")
    query.add_argument("query", help="Natural language query")
    query.set_defaults(func=cmd_query)

    graph = sub.add_parser("graph", help="Show graph neighbors for a company")
    graph.add_argument("company", help="Company slug")
    graph.set_defaults(func=cmd_graph)

    serve = sub.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    result = args.func(args)
    return int(result) if result is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
