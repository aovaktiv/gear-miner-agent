from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional
from urllib.request import Request, urlopen

from .extractors import JsonLdProductExtractor
from .history import WaybackCaptureIndex
from .models import (
    CrawlOutcome,
    CrawlStatus,
    GearCategory,
    HistoricalCapture,
    MineReport,
    ProductCandidate,
    SourceSeed,
    best_by_key,
)
from .seeds import get_sources, normalize_brand_name
from .store import write_snapshot


DEFAULT_HEADERS = {
    "User-Agent": "GearMinerBot/0.1 (+https://example.com/gear-miner)",
    "Accept-Language": "en-US,en;q=0.8",
}


FetchHtml = Callable[[str], str]


def default_fetch_html(url: str, timeout_seconds: int = 15) -> str:
    request = Request(url, headers=DEFAULT_HEADERS)
    with urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


class GearMinerAgent:
    def __init__(
        self,
        fetch_html: Optional[FetchHtml] = None,
        extractor: Optional[JsonLdProductExtractor] = None,
        capture_index: Optional[WaybackCaptureIndex] = None,
        default_start_year: int = 2020,
        default_end_year: Optional[int] = None,
    ) -> None:
        self.fetch_html = fetch_html or default_fetch_html
        self.extractor = extractor or JsonLdProductExtractor()
        self.capture_index = capture_index or WaybackCaptureIndex()
        self.default_start_year = default_start_year
        self.default_end_year = default_end_year or datetime.now(timezone.utc).year

    def mine_category(
        self,
        category: GearCategory,
        brand: Optional[str] = None,
        limit: Optional[int] = None,
        output_path: Optional[Path] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
    ) -> MineReport:
        seeds = get_sources(category, brand=brand)
        if limit is not None:
            seeds = seeds[:limit]
        return self.mine_sources(
            seeds,
            category=category,
            requested_brand=brand,
            output_path=output_path,
            search_start_year=start_year or self.default_start_year,
            search_end_year=end_year or self.default_end_year,
        )

    def mine_sources(
        self,
        seeds: Iterable[SourceSeed],
        category: GearCategory,
        requested_brand: Optional[str] = None,
        output_path: Optional[Path] = None,
        search_start_year: int = 2020,
        search_end_year: Optional[int] = None,
    ) -> MineReport:
        started_at = datetime.now(timezone.utc)
        resolved_end_year = search_end_year or datetime.now(timezone.utc).year
        products: List[ProductCandidate] = []
        outcomes: List[CrawlOutcome] = []

        for seed in seeds:
            extracted_count = 0
            successful_captures = 0
            errors: List[str] = []
            try:
                captures = self.capture_index.list_captures(
                    seed,
                    start_year=search_start_year,
                    end_year=resolved_end_year,
                )
            except Exception as exc:
                captures = [HistoricalCapture(timestamp="live", original_url=seed.url, archived_url=seed.url)]
                errors.append(f"archive lookup failed: {exc}")

            for capture in captures:
                try:
                    html = self.fetch_html(capture.archived_url)
                    extracted = self.extractor.extract(html, seed)
                    if requested_brand:
                        extracted = [
                            product for product in extracted if brands_match(product.brand, requested_brand)
                        ]
                    for product in extracted:
                        if capture.year is not None:
                            product.metadata.setdefault("historical_year", capture.year)
                        product.metadata.setdefault("historical_capture_timestamp", capture.timestamp)
                    products.extend(extracted)
                    extracted_count += len(extracted)
                    successful_captures += 1
                except Exception as exc:
                    errors.append(f"{capture.archived_url}: {exc}")

            if successful_captures:
                outcomes.append(
                    CrawlOutcome(
                        source=seed,
                        status=CrawlStatus.SUCCESS,
                        extracted_count=extracted_count,
                        capture_count=successful_captures,
                        error="; ".join(errors) if errors else None,
                    )
                )
            else:
                outcomes.append(
                    CrawlOutcome(
                        source=seed,
                        status=CrawlStatus.FAILED,
                        capture_count=0,
                        error="; ".join(errors) if errors else "no captures available",
                    )
                )

        report = MineReport(
            category=category,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            products=best_by_key(products),
            outcomes=outcomes,
            requested_brand=requested_brand.strip() if requested_brand else None,
            search_start_year=search_start_year,
            search_end_year=resolved_end_year,
        )

        if output_path is not None:
            write_snapshot(output_path, report)

        return report


def brands_match(candidate_brand: str, requested_brand: str) -> bool:
    return normalize_brand_name(candidate_brand) == normalize_brand_name(requested_brand)
