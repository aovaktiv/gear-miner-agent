from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
import re
from typing import Callable, List, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from .models import GearCategory, SourceKind, SourceSeed, normalize_text


SEARCH_HEADERS = {
    "User-Agent": "GearMinerBot/0.1 (+https://example.com/gear-miner)",
    "Accept-Language": "en-US,en;q=0.8",
}

ANCHOR_PATTERN = re.compile(r"<a(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
HREF_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)

TAG_PATTERN = re.compile(r"<[^>]+>")
BLOCKED_DOMAINS = {
    "duckduckgo.com",
    "www.duckduckgo.com",
    "google.com",
    "www.google.com",
    "bing.com",
    "www.bing.com",
    "search.yahoo.com",
}


FetchSearchHtml = Callable[[str], str]
DiscoveryProgressCallback = Callable[[int, int, str], None]


def default_fetch_search_html(url: str, timeout_seconds: int = 20) -> str:
    request = Request(url, headers=SEARCH_HEADERS)
    with urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


@dataclass
class DiscoveryReport:
    sources: List[SourceSeed] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    queries_attempted: int = 0


class LiveWebDiscovery:
    def __init__(self, fetch_search_html: Optional[FetchSearchHtml] = None) -> None:
        self.fetch_search_html = fetch_search_html or default_fetch_search_html

    def discover_sources(
        self,
        brand: str,
        category: GearCategory,
        limit: int = 20,
        progress_callback: Optional[DiscoveryProgressCallback] = None,
    ) -> DiscoveryReport:
        report = DiscoveryReport()
        seen_urls = set()
        queries = build_search_queries(brand, category)

        for index, query in enumerate(queries, start=1):
            if progress_callback:
                progress_callback(index - 1, len(queries), f"Searching live web: {query}")
            report.queries_attempted += 1
            try:
                html = self.fetch_search_html(build_duckduckgo_search_url(query))
                results = parse_search_results(html)
            except Exception as exc:
                report.errors.append(f"Search query failed for '{query}': {exc}")
                continue

            for result in results:
                normalized_url = normalize_result_url(result.url)
                if not normalized_url or normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)
                report.sources.append(source_seed_from_result(result, category=category, brand=brand))
                report.sources[-1] = SourceSeed(
                    name=report.sources[-1].name,
                    url=normalized_url,
                    kind=report.sources[-1].kind,
                    category=report.sources[-1].category,
                    brand=report.sources[-1].brand,
                    tags=report.sources[-1].tags,
                    notes=report.sources[-1].notes,
                )
                if len(report.sources) >= limit:
                    if progress_callback:
                        progress_callback(len(queries), len(queries), "Live search discovery complete")
                    return report

        if progress_callback:
            progress_callback(len(queries), len(queries), "Live search discovery complete")
        return report


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str


def build_search_queries(brand: str, category: GearCategory) -> List[str]:
    category_text = category.display_name
    return [
        f'"{brand}" "{category_text}"',
        f'"{brand}" "{category_text}" product',
        f'"{brand}" "{category_text}" buy',
    ]


def build_duckduckgo_search_url(query: str) -> str:
    return f"https://html.duckduckgo.com/html/?{urlencode({'q': query})}"


def parse_search_results(html: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    seen = set()
    for match in ANCHOR_PATTERN.finditer(html):
        attrs = match.group("attrs")
        if "result__a" not in attrs and "result-title-a" not in attrs:
            continue
        href_match = HREF_PATTERN.search(attrs)
        if not href_match:
            continue
        href = decode_search_result_url(unescape(href_match.group(1)))
        title = strip_tags(unescape(match.group("body")))
        normalized_url = normalize_result_url(href)
        if not normalized_url or normalized_url in seen:
            continue
        seen.add(normalized_url)
        results.append(SearchResult(url=normalized_url, title=title))
    return results


def decode_search_result_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [None])[0]
        if uddg:
            return unquote(uddg)
    if url.startswith("//"):
        return f"https:{url}"
    return url


def normalize_result_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() in BLOCKED_DOMAINS:
        return None
    return url


def strip_tags(value: str) -> str:
    return TAG_PATTERN.sub("", value).strip()


def source_seed_from_result(result: SearchResult, category: GearCategory, brand: str) -> SourceSeed:
    host = urlparse(result.url).netloc.lower()
    normalized_brand = normalize_text(brand).replace(" ", "")
    normalized_host = normalize_text(host).replace(" ", "")
    source_kind = SourceKind.BRAND if normalized_brand and normalized_brand in normalized_host else SourceKind.RETAILER
    title = result.title or host
    return SourceSeed(
        name=title,
        url=result.url,
        kind=source_kind,
        category=category,
        brand=brand if source_kind is SourceKind.BRAND else None,
        tags=("live-search",),
        notes="Discovered from live web search.",
    )
