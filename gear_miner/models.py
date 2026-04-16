from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "unknown"


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class GearCategory(str, Enum):
    RUNNING_SHOE = "running-shoe"

    @property
    def display_name(self) -> str:
        if self is GearCategory.RUNNING_SHOE:
            return "Running shoes"
        return self.value.replace("-", " ").title()

    @classmethod
    def parse(cls, value: str) -> "GearCategory":
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("Product category cannot be blank.")

        aliases = {
            cls.RUNNING_SHOE: {
                "running shoe",
                "running shoes",
                normalize_text(cls.RUNNING_SHOE.value),
                normalize_text(cls.RUNNING_SHOE.display_name),
            },
        }

        for category, allowed_values in aliases.items():
            if normalized in allowed_values:
                return category

        supported = ", ".join(category.display_name for category in cls)
        raise ValueError(f"Unsupported product category '{value}'. Supported categories: {supported}.")


class ExportFormat(str, Enum):
    CSV = "csv"
    EXCEL = "excel"

    @property
    def extension(self) -> str:
        if self is ExportFormat.CSV:
            return "csv"
        return "xlsx"

    @property
    def label(self) -> str:
        if self is ExportFormat.CSV:
            return "CSV"
        return "Excel"

    @property
    def content_type(self) -> str:
        if self is ExportFormat.CSV:
            return "text/csv; charset=utf-8"
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    @classmethod
    def parse(cls, value: str) -> "ExportFormat":
        normalized = normalize_text(value)
        aliases = {
            cls.CSV: {"csv", "comma separated values"},
            cls.EXCEL: {"excel", "xlsx", "spreadsheet"},
        }
        for export_format, allowed_values in aliases.items():
            if normalized in allowed_values:
                return export_format
        supported = ", ".join(option.label for option in cls)
        raise ValueError(f"Unsupported export format '{value}'. Supported formats: {supported}.")


class SourceKind(str, Enum):
    BRAND = "brand"
    RETAILER = "retailer"
    REVIEW = "review"
    MARKETPLACE = "marketplace"


class CrawlStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class HistoricalCapture:
    timestamp: str
    original_url: str
    archived_url: str

    @property
    def year(self) -> Optional[int]:
        if len(self.timestamp) >= 4 and self.timestamp[:4].isdigit():
            return int(self.timestamp[:4])
        return None


@dataclass(frozen=True)
class SourceSeed:
    name: str
    url: str
    kind: SourceKind
    category: GearCategory
    brand: Optional[str] = None
    tags: Tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "kind": self.kind.value,
            "category": self.category.value,
            "brand": self.brand,
            "tags": list(self.tags),
            "notes": self.notes,
        }


@dataclass
class ProductCandidate:
    source_name: str
    source_kind: SourceKind
    source_url: str
    product_url: str
    category: GearCategory
    name: str
    brand: str
    model: str
    sku: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    product_type: Optional[str] = None
    photo_url: Optional[str] = None
    photo_format: Optional[str] = None
    photo_path: Optional[str] = None
    extracted_from: str = "json-ld"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def canonical_key(self) -> str:
        return slugify(f"{self.category.value}-{self.brand}-{self.model}")

    def completeness_score(self) -> int:
        return sum(
            1
            for value in (
                self.sku,
                self.price,
                self.currency,
                self.product_type,
                self.metadata.get("image"),
            )
            if value not in (None, "", [])
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_key": self.canonical_key,
            "source_name": self.source_name,
            "source_kind": self.source_kind.value,
            "source_url": self.source_url,
            "product_url": self.product_url,
            "category": self.category.value,
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "sku": self.sku,
            "price": self.price,
            "currency": self.currency,
            "product_type": self.product_type,
            "photo_url": self.photo_url,
            "photo_format": self.photo_format,
            "photo_path": self.photo_path,
            "extracted_from": self.extracted_from,
            "metadata": self.metadata,
        }


@dataclass
class CrawlOutcome:
    source: SourceSeed
    status: CrawlStatus
    extracted_count: int = 0
    capture_count: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "status": self.status.value,
            "extracted_count": self.extracted_count,
            "capture_count": self.capture_count,
            "error": self.error,
        }


@dataclass
class MineReport:
    category: GearCategory
    started_at: datetime
    finished_at: datetime
    products: List[ProductCandidate]
    outcomes: List[CrawlOutcome]
    requested_brand: Optional[str] = None
    search_mode: str = "historical"
    live_queries_attempted: int = 0
    search_start_year: int = 2020
    search_end_year: int = field(default_factory=lambda: datetime.utcnow().year)
    warnings: List[str] = field(default_factory=list)

    @property
    def attempted_sources(self) -> int:
        return len(self.outcomes)

    @property
    def succeeded_sources(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is CrawlStatus.SUCCESS)

    @property
    def failed_sources(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is CrawlStatus.FAILED)

    @property
    def unique_models(self) -> int:
        return len({product.canonical_key for product in self.products})

    @property
    def pages_crawled(self) -> int:
        return sum(outcome.capture_count for outcome in self.outcomes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "requested_brand": self.requested_brand,
            "search_mode": self.search_mode,
            "live_queries_attempted": self.live_queries_attempted,
            "search_start_year": self.search_start_year,
            "search_end_year": self.search_end_year,
            "warnings": list(self.warnings),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "summary": {
                "attempted_sources": self.attempted_sources,
                "succeeded_sources": self.succeeded_sources,
                "failed_sources": self.failed_sources,
                "products": len(self.products),
                "unique_models": self.unique_models,
                "pages_crawled": self.pages_crawled,
                "warning_count": len(self.warnings),
            },
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "products": [product.to_dict() for product in self.products],
        }


def best_by_key(products: Sequence[ProductCandidate]) -> List[ProductCandidate]:
    best: Dict[Tuple[str, str], ProductCandidate] = {}
    for product in products:
        key = (product.source_name.lower(), product.product_url or product.canonical_key)
        current = best.get(key)
        if current is None or product.completeness_score() > current.completeness_score():
            best[key] = product
    return list(best.values())
