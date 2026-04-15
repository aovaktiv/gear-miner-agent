from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from .models import GearCategory, SourceSeed
from .pipeline import GearMinerAgent
from .seeds import get_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gear-miner",
        description="Mine gear data from the web, starting with running shoes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_sources_parser = subparsers.add_parser(
        "list-sources",
        help="List the configured crawl sources for a category.",
    )
    list_sources_parser.add_argument(
        "--category",
        default=GearCategory.RUNNING_SHOE.value,
        choices=[category.value for category in GearCategory],
    )

    mine_parser = subparsers.add_parser(
        "mine",
        help="Run a mining pass for a category.",
    )
    mine_parser.add_argument(
        "--category",
        default=GearCategory.RUNNING_SHOE.value,
        choices=[category.value for category in GearCategory],
    )
    mine_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only crawl the first N configured sources.",
    )
    mine_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to save the snapshot JSON.",
    )
    return parser


def list_sources(sources: Iterable[SourceSeed]) -> None:
    for source in sources:
        print(f"{source.name} [{source.kind.value}]")
        print(f"  {source.url}")


def run_mine(category: GearCategory, limit: Optional[int], output: Optional[Path]) -> int:
    agent = GearMinerAgent()
    report = agent.mine_category(category=category, limit=limit, output_path=output)

    print(f"Category: {report.category.value}")
    print(f"Attempted sources: {report.attempted_sources}")
    print(f"Successful sources: {report.succeeded_sources}")
    print(f"Failed sources: {report.failed_sources}")
    print(f"Products extracted: {len(report.products)}")
    print(f"Unique models: {report.unique_models}")

    failed = [outcome for outcome in report.outcomes if outcome.error]
    for outcome in failed:
        print(f"Failed: {outcome.source.name} -> {outcome.error}")

    if output is not None:
        print(f"Snapshot saved to: {output}")

    return 0 if report.succeeded_sources else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    category = GearCategory(args.category)

    if args.command == "list-sources":
        list_sources(get_sources(category))
        return 0

    if args.command == "mine":
        return run_mine(category=category, limit=args.limit, output=args.output)

    parser.error(f"Unknown command: {args.command}")
    return 2
