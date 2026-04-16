from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from .models import GearCategory, SourceSeed
from .pipeline import GearMinerAgent
from .seeds import get_sources
from .ui import serve_ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gear-miner",
        description="Mine live gear data from the web, starting with running shoes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_sources_parser = subparsers.add_parser(
        "list-sources",
        help="List the configured crawl sources for a category.",
    )
    list_sources_parser.add_argument(
        "--category",
        default=GearCategory.RUNNING_SHOE.display_name,
        help="Product category such as 'Running shoes'.",
    )
    list_sources_parser.add_argument(
        "--brand",
        default=None,
        help="Optional brand filter such as Nike or adidas.",
    )

    mine_parser = subparsers.add_parser(
        "mine",
        help="Run a live mining pass with prompted brand/category inputs when needed.",
    )
    mine_parser.add_argument(
        "--brand",
        default=None,
        help="Brand name such as Nike or adidas. If omitted, the CLI prompts for it.",
    )
    mine_parser.add_argument(
        "--category",
        default=None,
        help="Product category such as 'Running shoes'. If omitted, the CLI prompts for it.",
    )
    mine_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only crawl the first N discovered or configured sources.",
    )
    mine_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the snapshot JSON.",
    )

    ui_parser = subparsers.add_parser(
        "ui",
        help="Launch the local browser UI for prompting and managing mining runs.",
    )
    ui_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface for the local UI server.",
    )
    ui_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for the local UI server.",
    )
    ui_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/ui"),
        help="Directory for UI state, snapshots, and exports.",
    )
    return parser


def list_sources(sources: Iterable[SourceSeed]) -> None:
    for source in sources:
        print(f"{source.name} [{source.kind.value}]")
        print(f"  {source.url}")


def prompt_for_value(prompt_label: str) -> str:
    while True:
        value = input(f"{prompt_label}: ").strip()
        if value:
            return value
        print("A value is required to continue.")


def resolve_category(raw_value: Optional[str], parser: argparse.ArgumentParser, prompt_if_missing: bool) -> GearCategory:
    value = raw_value
    if prompt_if_missing and not value:
        value = prompt_for_value("Step 2: Enter product category")

    if value is None:
        value = GearCategory.RUNNING_SHOE.display_name

    try:
        return GearCategory.parse(value)
    except ValueError as exc:
        parser.error(str(exc))
        raise AssertionError("parser.error should exit")


def resolve_brand(raw_value: Optional[str], prompt_if_missing: bool) -> Optional[str]:
    value = raw_value.strip() if raw_value else ""
    if prompt_if_missing and not value:
        value = prompt_for_value("Step 1: Enter brand name")
    return value or None


def run_mine(
    category: GearCategory,
    brand: Optional[str],
    limit: Optional[int],
    output: Optional[Path],
) -> int:
    agent = GearMinerAgent()
    report = agent.mine_category(
        category=category,
        brand=brand,
        limit=limit,
        output_path=output,
    )

    if report.requested_brand:
        print(f"Brand: {report.requested_brand}")
    print(f"Category: {report.category.display_name}")
    print(f"Search mode: {report.search_mode}")
    if report.live_queries_attempted:
        print(f"Live queries attempted: {report.live_queries_attempted}")
    print(f"Attempted sources: {report.attempted_sources}")
    print(f"Successful sources: {report.succeeded_sources}")
    print(f"Failed sources: {report.failed_sources}")
    print(f"Products extracted: {len(report.products)}")
    print(f"Unique models: {report.unique_models}")
    if report.warnings:
        print(f"Warnings: {len(report.warnings)}")

    failed = [outcome for outcome in report.outcomes if outcome.error]
    for outcome in failed:
        print(f"Failed: {outcome.source.name} -> {outcome.error}")

    for warning in report.warnings:
        print(f"Warning: {warning}")

    if output is not None:
        print(f"Snapshot saved to: {output}")

    return 0 if report.succeeded_sources else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-sources":
        category = resolve_category(args.category, parser=parser, prompt_if_missing=False)
        list_sources(get_sources(category, brand=args.brand))
        return 0

    if args.command == "mine":
        brand = resolve_brand(args.brand, prompt_if_missing=True)
        category = resolve_category(args.category, parser=parser, prompt_if_missing=True)
        return run_mine(category=category, brand=brand, limit=args.limit, output=args.output)

    if args.command == "ui":
        return serve_ui(host=args.host, port=args.port, data_dir=args.data_dir)

    parser.error(f"Unknown command: {args.command}")
    return 2
