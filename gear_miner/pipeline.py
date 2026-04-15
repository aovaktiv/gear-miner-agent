from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional
from urllib.request import Request, urlopen

from .extractors import JsonLdProductExtractor
from .models import CrawlOutcome, CrawlStatus, GearCategory, MineReport, ProductCandidate, SourceSeed, best_by_key
from .seeds import get_sources
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
    ) -> None:
        self.fetch_html = fetch_html or default_fetch_html
        self.extractor = extractor or JsonLdProductExtractor()

    def mine_category(
        self,
        category: GearCategory,
        limit: Optional[int] = None,
        output_path: Optional[Path] = None,
    ) -> MineReport:
        seeds = get_sources(category)
        if limit is not None:
            seeds = seeds[:limit]
        return self.mine_sources(seeds, category=category, output_path=output_path)

    def mine_sources(
        self,
        seeds: Iterable[SourceSeed],
        category: GearCategory,
        output_path: Optional[Path] = None,
    ) -> MineReport:
        started_at = datetime.now(timezone.utc)
        products: List[ProductCandidate] = []
        outcomes: List[CrawlOutcome] = []

        for seed in seeds:
            try:
                html = self.fetch_html(seed.url)
                extracted = self.extractor.extract(html, seed)
                products.extend(extracted)
                outcomes.append(
                    CrawlOutcome(
                        source=seed,
                        status=CrawlStatus.SUCCESS,
                        extracted_count=len(extracted),
                    )
                )
            except Exception as exc:
                outcomes.append(
                    CrawlOutcome(
                        source=seed,
                        status=CrawlStatus.FAILED,
                        error=str(exc),
                    )
                )

        report = MineReport(
            category=category,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            products=best_by_key(products),
            outcomes=outcomes,
        )

        if output_path is not None:
            write_snapshot(output_path, report)

        return report
