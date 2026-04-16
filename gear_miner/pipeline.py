from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence
from urllib.request import Request, urlopen

from .crawler import CrawlCancelled, CrawlSettings, MultiPageCrawler
from .domains import is_url_allowed, parse_domain_list
from .extractors import JsonLdProductExtractor
from .history import WaybackCaptureIndex
from .live_search import LiveWebDiscovery
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
ShouldCancel = Callable[[], bool]
ProgressCallback = Callable[[int, int, str], None]


class MiningCancelled(Exception):
    pass


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
        live_discovery: Optional[LiveWebDiscovery] = None,
        default_start_year: int = 2020,
        default_end_year: Optional[int] = None,
        should_cancel: Optional[ShouldCancel] = None,
        progress_callback: Optional[ProgressCallback] = None,
        default_live_source_limit: int = 12,
        default_live_page_limit: int = 6,
        default_live_crawl_depth: int = 2,
    ) -> None:
        self.fetch_html = fetch_html or default_fetch_html
        self.extractor = extractor or JsonLdProductExtractor()
        self.capture_index = capture_index or WaybackCaptureIndex()
        self.live_discovery = live_discovery or LiveWebDiscovery()
        self.default_start_year = default_start_year
        self.default_end_year = default_end_year or datetime.now(timezone.utc).year
        self.should_cancel = should_cancel or (lambda: False)
        self.progress_callback = progress_callback or (lambda _current, _total, _label: None)
        self.default_live_source_limit = default_live_source_limit
        self.default_live_page_limit = default_live_page_limit
        self.default_live_crawl_depth = default_live_crawl_depth

    def mine_category(
        self,
        category: GearCategory,
        brand: Optional[str] = None,
        limit: Optional[int] = None,
        output_path: Optional[Path] = None,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        allow_domains: Sequence[str] | str | None = None,
        block_domains: Sequence[str] | str | None = None,
    ) -> MineReport:
        return self.mine_live_category(
            category=category,
            brand=brand,
            limit=limit,
            output_path=output_path,
            allow_domains=allow_domains,
            block_domains=block_domains,
        )

    def mine_live_category(
        self,
        category: GearCategory,
        brand: Optional[str] = None,
        limit: Optional[int] = None,
        output_path: Optional[Path] = None,
        allow_domains: Sequence[str] | str | None = None,
        block_domains: Sequence[str] | str | None = None,
    ) -> MineReport:
        source_limit = limit or self.default_live_source_limit
        parsed_allow_domains = parse_domain_list(allow_domains)
        parsed_block_domains = parse_domain_list(block_domains)
        warnings: List[str] = []
        configured_sources = get_sources(category, brand=brand)
        discovered_sources = []
        queries_attempted = 0

        self._report_progress(2, 100, "Preparing live web search")
        if brand:
            discovery_report = self.live_discovery.discover_sources(
                brand=brand,
                category=category,
                limit=source_limit,
                allow_domains=parsed_allow_domains,
                block_domains=parsed_block_domains,
                progress_callback=lambda current, total, label: self._report_weighted_progress(
                    5,
                    25,
                    current,
                    total,
                    label,
                ),
            )
            discovered_sources = discovery_report.sources
            queries_attempted = discovery_report.queries_attempted
            warnings.extend(discovery_report.errors)
        else:
            warnings.append("No brand was provided, so live search discovery was skipped.")

        seeds = merge_sources(discovered_sources, configured_sources, limit=source_limit)
        filtered_seeds = filter_sources_by_domains(
            seeds,
            allow_domains=parsed_allow_domains,
            block_domains=parsed_block_domains,
        )
        if len(filtered_seeds) < len(seeds):
            warnings.append("Some sources were skipped because of the current domain allow/block controls.")
        seeds = filtered_seeds
        if not seeds:
            raise ValueError("No live sources matched the current domain allow/block controls.")
        if discovered_sources:
            self._report_progress(28, 100, f"Discovered {len(discovered_sources)} live web sources")
        elif seeds:
            warnings.append("No live web results were discovered. Falling back to configured sources.")
            self._report_progress(28, 100, "No live results found, falling back to configured sources")
        else:
            raise ValueError("No live sources were available for that search.")

        report = self.mine_live_sources(
            seeds,
            category=category,
            requested_brand=brand,
            output_path=output_path,
            warnings=warnings,
            queries_attempted=queries_attempted,
            allow_domains=parsed_allow_domains,
            block_domains=parsed_block_domains,
        )
        self._report_progress(80, 100, "Live crawling complete")
        return report

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
            self._raise_if_cancelled()
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
                self._raise_if_cancelled()
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
                    self._raise_if_cancelled()
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

        self._raise_if_cancelled()
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

    def mine_live_sources(
        self,
        seeds: Iterable[SourceSeed],
        category: GearCategory,
        requested_brand: Optional[str] = None,
        output_path: Optional[Path] = None,
        warnings: Optional[List[str]] = None,
        queries_attempted: int = 0,
        allow_domains: Sequence[str] = (),
        block_domains: Sequence[str] = (),
    ) -> MineReport:
        started_at = datetime.now(timezone.utc)
        products: List[ProductCandidate] = []
        outcomes: List[CrawlOutcome] = []
        seed_list = list(seeds)
        total_sources = len(seed_list)
        crawler = MultiPageCrawler(
            fetch_html=self.fetch_html,
            extractor=self.extractor,
            should_cancel=self.should_cancel,
        )
        crawl_settings = CrawlSettings(
            allow_domains=allow_domains,
            block_domains=block_domains,
            max_pages_per_source=self.default_live_page_limit,
            max_depth=self.default_live_crawl_depth,
        )

        if total_sources == 0:
            raise ValueError("No live sources were available to crawl.")

        for index, seed in enumerate(seed_list, start=1):
            self._raise_if_cancelled()
            try:
                crawl_result = crawler.crawl_source(
                    seed=seed,
                    category=category,
                    requested_brand=requested_brand,
                    settings=crawl_settings,
                    progress_callback=lambda current, total, label, index=index, total_sources=total_sources: self._report_live_source_progress(
                        source_index=index,
                        total_sources=total_sources,
                        current_page=current,
                        total_pages=total,
                        label=label,
                    ),
                )
                products.extend(crawl_result.products)
                outcome_status = CrawlStatus.SUCCESS if crawl_result.pages_crawled else CrawlStatus.FAILED
                outcomes.append(
                    CrawlOutcome(
                        source=seed,
                        status=outcome_status,
                        extracted_count=len(crawl_result.products),
                        capture_count=crawl_result.pages_crawled,
                        error=(
                            "; ".join(crawl_result.errors)
                            if crawl_result.errors
                            else (None if crawl_result.pages_crawled else "no pages crawled")
                        ),
                    )
                )
            except CrawlCancelled as exc:
                raise MiningCancelled() from exc
            except Exception as exc:
                outcomes.append(
                    CrawlOutcome(
                        source=seed,
                        status=CrawlStatus.FAILED,
                        capture_count=0,
                        error=str(exc),
                    )
                )

        self._raise_if_cancelled()
        report = MineReport(
            category=category,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            products=best_by_key(products),
            outcomes=outcomes,
            requested_brand=requested_brand.strip() if requested_brand else None,
            search_mode="live",
            live_queries_attempted=queries_attempted,
            search_start_year=datetime.now(timezone.utc).year,
            search_end_year=datetime.now(timezone.utc).year,
            warnings=list(warnings or []),
        )

        if output_path is not None:
            write_snapshot(output_path, report)

        return report

    def _raise_if_cancelled(self) -> None:
        if self.should_cancel():
            raise MiningCancelled()

    def _report_progress(self, current: int, total: int, label: str) -> None:
        self.progress_callback(max(current, 0), max(total, 1), label)

    def _report_weighted_progress(
        self,
        start: int,
        end: int,
        current: int,
        total: int,
        label: str,
    ) -> None:
        if total <= 0:
            self._report_progress(end, 100, label)
            return
        clamped_current = min(max(current, 0), total)
        progress = start + int(((end - start) * clamped_current) / total)
        self._report_progress(progress, 100, label)

    def _report_live_source_progress(
        self,
        source_index: int,
        total_sources: int,
        current_page: int,
        total_pages: int,
        label: str,
    ) -> None:
        total_expected_pages = max(total_sources * self.default_live_page_limit, 1)
        absolute_current = min(
            ((source_index - 1) * self.default_live_page_limit) + max(current_page, 0),
            total_expected_pages,
        )
        self._report_weighted_progress(30, 80, absolute_current, total_expected_pages, label)


def brands_match(candidate_brand: str, requested_brand: str) -> bool:
    return normalize_brand_name(candidate_brand) == normalize_brand_name(requested_brand)


def merge_sources(
    discovered_sources: Iterable[SourceSeed],
    configured_sources: Iterable[SourceSeed],
    limit: Optional[int] = None,
) -> List[SourceSeed]:
    merged: List[SourceSeed] = []
    seen_urls = set()

    for seed in list(discovered_sources) + list(configured_sources):
        if seed.url in seen_urls:
            continue
        seen_urls.add(seed.url)
        merged.append(seed)
        if limit is not None and len(merged) >= limit:
            break

    return merged


def filter_sources_by_domains(
    seeds: Iterable[SourceSeed],
    allow_domains: Sequence[str] = (),
    block_domains: Sequence[str] = (),
) -> List[SourceSeed]:
    if not allow_domains and not block_domains:
        return list(seeds)

    filtered = []
    for seed in seeds:
        if is_url_allowed(seed.url, allow_domains=allow_domains, block_domains=block_domains):
            filtered.append(seed)
    return filtered
