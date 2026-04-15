from __future__ import annotations

from typing import Dict, List, Optional

from .models import GearCategory, SourceKind, SourceSeed, normalize_text


KNOWN_RUNNING_SHOE_BRANDS = (
    "New Balance",
    "Brooks",
    "Saucony",
    "ASICS",
    "Nike",
    "adidas",
    "HOKA",
    "Mizuno",
    "On",
    "PUMA",
    "Altra",
)


RUNNING_SHOE_SEEDS = [
    SourceSeed(
        name="Nike Running",
        url="https://www.nike.com/w/running-shoes-37v7jzy7ok",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        brand="Nike",
        tags=("brand", "direct"),
        notes="Direct brand source for road and training models.",
    ),
    SourceSeed(
        name="adidas Running",
        url="https://www.adidas.com/us/running-shoes",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        brand="adidas",
        tags=("brand", "direct"),
        notes="Direct brand source for running footwear.",
    ),
    SourceSeed(
        name="HOKA Running",
        url="https://www.hoka.com/en/us/running-shoes/",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        brand="HOKA",
        tags=("brand", "direct"),
        notes="Direct brand source for performance running shoes.",
    ),
    SourceSeed(
        name="Brooks Running",
        url="https://www.brooksrunning.com/en_us/mens-road-running-shoes/",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        brand="Brooks",
        tags=("brand", "direct"),
        notes="Direct brand source focused on road shoes.",
    ),
    SourceSeed(
        name="Saucony Running",
        url="https://www.saucony.com/en/running-shoes/",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        brand="Saucony",
        tags=("brand", "direct"),
        notes="Direct brand source for daily trainers and racers.",
    ),
    SourceSeed(
        name="Running Warehouse",
        url="https://www.runningwarehouse.com/catpage-MRSHOE.html",
        kind=SourceKind.RETAILER,
        category=GearCategory.RUNNING_SHOE,
        tags=("retailer", "multi-brand"),
        notes="Retail catalog with broad brand coverage.",
    ),
    SourceSeed(
        name="REI Running Shoes",
        url="https://www.rei.com/c/mens-running-shoes",
        kind=SourceKind.RETAILER,
        category=GearCategory.RUNNING_SHOE,
        tags=("retailer", "multi-brand"),
        notes="Retail source for mainstream running models.",
    ),
]


SEEDS_BY_CATEGORY: Dict[GearCategory, List[SourceSeed]] = {
    GearCategory.RUNNING_SHOE: RUNNING_SHOE_SEEDS,
}


def normalize_brand_name(brand: str) -> str:
    return normalize_text(brand)


def get_sources(category: GearCategory, brand: Optional[str] = None) -> List[SourceSeed]:
    seeds = list(SEEDS_BY_CATEGORY.get(category, []))
    if not brand:
        return seeds

    normalized_brand = normalize_brand_name(brand)
    direct_brand_sources = [
        seed for seed in seeds if seed.brand and normalize_brand_name(seed.brand) == normalized_brand
    ]
    shared_sources = [seed for seed in seeds if seed.brand is None]

    if direct_brand_sources:
        return direct_brand_sources + shared_sources
    if shared_sources:
        return shared_sources
    return seeds
