from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, Iterable, List, Optional, Sequence
from urllib.parse import parse_qs, urljoin, urldefrag, urlparse

from .domains import is_url_allowed, url_host
from .extractors import JsonLdProductExtractor
from .models import GearCategory, ProductCandidate, SourceSeed, normalize_text


ShouldCancel = Callable[[], bool]
PageProgressCallback = Callable[[int, int, str], None]

ASSET_SUFFIXES = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".zip",
)

PAGINATION_TOKENS = ("next", "older", "newer", "more", "page", "view more")
PRODUCTISH_TOKENS = ("product", "products", "shoe", "shoes", "running", "road", "trail")


class CrawlCancelled(Exception):
    pass


@dataclass(frozen=True)
class CrawlSettings:
    allow_domains: Sequence[str] = ()
    block_domains: Sequence[str] = ()
    max_pages_per_source: int = 6
    max_depth: int = 2
    max_links_per_page: int = 16


@dataclass
class SourceCrawlResult:
    products: List[ProductCandidate] = field(default_factory=list)
    pages_crawled: int = 0
    errors: List[str] = field(default_factory=list)
    visited_urls: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class HtmlLink:
    url: str
    text: str


class MultiPageCrawler:
    def __init__(
        self,
        fetch_html: Callable[[str], str],
        extractor: Optional[JsonLdProductExtractor] = None,
        should_cancel: Optional[ShouldCancel] = None,
    ) -> None:
        self.fetch_html = fetch_html
        self.extractor = extractor or JsonLdProductExtractor()
        self.should_cancel = should_cancel or (lambda: False)

    def crawl_source(
        self,
        seed: SourceSeed,
        category: GearCategory,
        requested_brand: Optional[str],
        settings: CrawlSettings,
        progress_callback: Optional[PageProgressCallback] = None,
    ) -> SourceCrawlResult:
        result = SourceCrawlResult()
        source_host = url_host(seed.url)
        queue = deque([(seed.url, 0)])
        queued = {seed.url}
        visited = set()

        while queue and result.pages_crawled < settings.max_pages_per_source:
            self._raise_if_cancelled()
            current_url, depth = queue.popleft()
            if current_url in visited:
                continue

            visited.add(current_url)
            result.visited_urls.append(current_url)
            if progress_callback:
                progress_callback(
                    result.pages_crawled,
                    settings.max_pages_per_source,
                    f"Crawling {seed.name}: page {result.pages_crawled + 1} of {settings.max_pages_per_source}",
                )

            try:
                html = self.fetch_html(current_url)
            except Exception as exc:
                result.errors.append(f"{current_url}: {exc}")
                continue

            result.pages_crawled += 1
            page_seed = SourceSeed(
                name=seed.name,
                url=current_url,
                kind=seed.kind,
                category=seed.category,
                brand=seed.brand,
                tags=seed.tags,
                notes=seed.notes,
            )
            extracted = self.extractor.extract(html, page_seed)
            for product in extracted:
                product.metadata.setdefault("crawled_page", current_url)
            if requested_brand:
                normalized_requested_brand = normalize_text(requested_brand)
                extracted = [
                    product
                    for product in extracted
                    if normalize_text(product.brand) == normalized_requested_brand
                ]
            result.products.extend(extracted)

            if depth >= settings.max_depth:
                continue

            candidates = prioritize_links(
                extract_links(html, current_url),
                category=category,
                brand=requested_brand or seed.brand,
                allow_domains=settings.allow_domains,
                block_domains=settings.block_domains,
                source_host=source_host,
            )
            for link in candidates[: settings.max_links_per_page]:
                if link in visited or link in queued:
                    continue
                queue.append((link, depth + 1))
                queued.add(link)

        if progress_callback:
            progress_callback(
                result.pages_crawled,
                max(settings.max_pages_per_source, 1),
                f"Crawling complete for {seed.name}",
            )
        return result

    def _raise_if_cancelled(self) -> None:
        if self.should_cancel():
            raise CrawlCancelled()


def extract_links(html: str, base_url: str) -> List[HtmlLink]:
    parser = _AnchorParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    return parser.links


def prioritize_links(
    links: Iterable[HtmlLink],
    category: GearCategory,
    brand: Optional[str],
    allow_domains: Sequence[str],
    block_domains: Sequence[str],
    source_host: str,
) -> List[str]:
    category_tokens = normalize_text(category.display_name).split()
    brand_tokens = normalize_text(brand or "").split()
    prioritized = []
    seen = set()

    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)

        if not is_candidate_url(link.url):
            continue
        if not is_url_allowed(link.url, allow_domains=allow_domains, block_domains=block_domains, default_host=source_host):
            continue

        score = link_priority(link, category_tokens, brand_tokens)
        if score is None:
            continue
        prioritized.append((score, link.url))

    prioritized.sort(key=lambda item: (item[0], item[1]))
    return [url for _, url in prioritized]


def is_candidate_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.lower()
    return not any(path.endswith(suffix) for suffix in ASSET_SUFFIXES)


def link_priority(link: HtmlLink, category_tokens: Sequence[str], brand_tokens: Sequence[str]) -> Optional[int]:
    combined = normalize_text(f"{link.url} {link.text}")
    parsed = urlparse(link.url)
    query = parse_qs(parsed.query)

    if any(key in query for key in ("page", "p", "offset", "start")):
        return 0
    if "/page/" in parsed.path.lower():
        return 0
    if any(token in combined for token in PAGINATION_TOKENS):
        return 0

    relevant_tokens = [token for token in category_tokens + list(brand_tokens) if token]
    if relevant_tokens and any(token in combined for token in relevant_tokens):
        if "/product" in parsed.path.lower() or "/products/" in parsed.path.lower():
            return 1
        return 2

    if any(token in combined for token in PRODUCTISH_TOKENS):
        return 3

    return None


class _AnchorParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: List[HtmlLink] = []
        self._current_href: Optional[str] = None
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value for name, value in attrs}
        href = attr_map.get("href")
        if not href:
            return
        resolved = normalize_link_url(href, self.base_url)
        if not resolved:
            return
        self._current_href = resolved
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is None:
            return
        self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = " ".join(part.strip() for part in self._current_text if part.strip()).strip()
        self.links.append(HtmlLink(url=self._current_href, text=text))
        self._current_href = None
        self._current_text = []


def normalize_link_url(href: str, base_url: str) -> Optional[str]:
    value = (href or "").strip()
    if not value or value.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    resolved = urljoin(base_url, value)
    resolved, _ = urldefrag(resolved)
    return resolved
