from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .extractors import infer_photo_format
from .models import ProductCandidate, slugify


PHOTO_HEADERS = {
    "User-Agent": "GearMinerBot/0.1 (+https://example.com/gear-miner)",
}


FetchPhoto = Callable[[str], tuple[bytes, Optional[str]]]
PhotoProgressCallback = Callable[[int, int, str], None]


def default_fetch_photo(url: str, timeout_seconds: int = 20) -> tuple[bytes, Optional[str]]:
    request = Request(url, headers=PHOTO_HEADERS)
    with urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get_content_type()
        return response.read(), content_type


@dataclass
class PhotoDownloadResult:
    saved_count: int = 0
    skipped_count: int = 0
    errors: List[str] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class ProductPhotoStore:
    def __init__(self, fetch_photo: Optional[FetchPhoto] = None) -> None:
        self.fetch_photo = fetch_photo or default_fetch_photo

    def save_product_photos(
        self,
        products: Iterable[ProductCandidate],
        output_dir: Path,
        progress_callback: Optional[PhotoProgressCallback] = None,
    ) -> PhotoDownloadResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        result = PhotoDownloadResult()
        items = list(products)
        total = len(items)

        if total == 0 and progress_callback:
            progress_callback(1, 1, "No product photos to save")

        for index, product in enumerate(items, start=1):
            photo_url = product.photo_url
            photo_format = infer_photo_format(photo_url) or product.photo_format
            if progress_callback:
                progress_callback(index - 1, max(total, 1), f"Saving product photo {index} of {total}")
            if not photo_url or photo_format not in {"jpg", "png"}:
                result.skipped_count += 1
                continue

            try:
                payload, content_type = self.fetch_photo(photo_url)
            except Exception as exc:
                result.skipped_count += 1
                result.errors.append(f"{photo_url}: {exc}")
                continue
            resolved_format = normalize_photo_format(photo_format, content_type)
            if resolved_format not in {"jpg", "png"}:
                result.skipped_count += 1
                continue

            filename = build_photo_filename(product, index=index, extension=resolved_format)
            photo_path = output_dir / filename
            photo_path.write_bytes(payload)

            product.photo_format = resolved_format
            product.photo_path = str(photo_path)
            result.saved_count += 1

        if progress_callback:
            progress_callback(max(total, 1), max(total, 1), "Product photo saving complete")

        return result


def normalize_photo_format(photo_format: Optional[str], content_type: Optional[str]) -> Optional[str]:
    if photo_format in {"jpg", "png"}:
        return photo_format
    if content_type == "image/jpeg":
        return "jpg"
    if content_type == "image/png":
        return "png"
    return None


def build_photo_filename(product: ProductCandidate, index: int, extension: str) -> str:
    base = slugify(f"{product.brand}-{product.name}") or f"product-{index}"
    return f"{base}-{index}.{extension}"
