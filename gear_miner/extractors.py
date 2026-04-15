from __future__ import annotations

from html import unescape
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from .models import ProductCandidate, SourceSeed
from .seeds import KNOWN_RUNNING_SHOE_BRANDS


JSON_LD_PATTERN = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


class JsonLdProductExtractor:
    def extract(self, html: str, seed: SourceSeed) -> List[ProductCandidate]:
        products: List[ProductCandidate] = []
        for payload in self._iter_json_ld_payloads(html):
            for item in self._iter_nodes(payload):
                if not self._is_product(item):
                    continue
                candidate = self._build_candidate(item, seed)
                if candidate is not None:
                    products.append(candidate)
        return products

    def _iter_json_ld_payloads(self, html: str) -> Iterable[Any]:
        for match in JSON_LD_PATTERN.finditer(html):
            raw_block = unescape(match.group(1)).strip()
            if not raw_block:
                continue
            try:
                yield json.loads(raw_block)
            except json.JSONDecodeError:
                continue

    def _iter_nodes(self, payload: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(payload, list):
            for item in payload:
                yield from self._iter_nodes(item)
            return
        if not isinstance(payload, dict):
            return
        if "@graph" in payload:
            yield from self._iter_nodes(payload["@graph"])
        else:
            yield payload

    def _is_product(self, item: Dict[str, Any]) -> bool:
        raw_type = item.get("@type")
        if isinstance(raw_type, list):
            types = {str(value).lower() for value in raw_type}
        else:
            types = {str(raw_type).lower()} if raw_type else set()
        return "product" in types

    def _build_candidate(
        self,
        item: Dict[str, Any],
        seed: SourceSeed,
    ) -> Optional[ProductCandidate]:
        name = self._clean_string(item.get("name"))
        if not name:
            return None

        brand = self._extract_brand(item) or infer_brand_from_name(name)
        if not brand:
            brand = "Unknown"

        model = strip_brand_prefix(name, brand) or name
        offers = item.get("offers")
        offer = self._extract_offer(offers)
        product_url = self._clean_string(item.get("url")) or seed.url

        metadata = {}
        if item.get("image"):
            metadata["image"] = item.get("image")
        if item.get("color"):
            metadata["color"] = item.get("color")

        return ProductCandidate(
            source_name=seed.name,
            source_kind=seed.kind,
            source_url=seed.url,
            product_url=product_url,
            category=seed.category,
            name=name,
            brand=brand,
            model=model,
            sku=self._clean_string(item.get("sku") or item.get("mpn")),
            price=coerce_price(offer.get("price")) if offer else None,
            currency=self._clean_string(offer.get("priceCurrency")) if offer else None,
            product_type=self._clean_string(item.get("category")),
            extracted_from="json-ld",
            metadata=metadata,
        )

    def _extract_brand(self, item: Dict[str, Any]) -> Optional[str]:
        brand = item.get("brand")
        if isinstance(brand, str):
            return self._clean_string(brand)
        if isinstance(brand, dict):
            return self._clean_string(brand.get("name"))
        return None

    def _extract_offer(self, offers: Any) -> Optional[Dict[str, Any]]:
        if isinstance(offers, dict):
            return offers
        if isinstance(offers, list):
            for offer in offers:
                if isinstance(offer, dict):
                    return offer
        return None

    def _clean_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def infer_brand_from_name(name: str) -> Optional[str]:
    lowered = name.lower()
    for brand in sorted(KNOWN_RUNNING_SHOE_BRANDS, key=len, reverse=True):
        if lowered.startswith(brand.lower()):
            return brand
    return None


def strip_brand_prefix(name: str, brand: str) -> str:
    pattern = re.compile(rf"^{re.escape(brand)}[\s\-:]+", re.IGNORECASE)
    stripped = pattern.sub("", name).strip()
    return stripped or name


def coerce_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None
