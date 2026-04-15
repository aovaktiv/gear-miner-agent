from __future__ import annotations

from typing import Dict, List

from .models import GearCategory, SourceKind, SourceSeed


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
        tags=("brand", "direct"),
        notes="Direct brand source for road and training models.",
    ),
    SourceSeed(
        name="adidas Running",
        url="https://www.adidas.com/us/running-shoes",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        tags=("brand", "direct"),
        notes="Direct brand source for running footwear.",
    ),
    SourceSeed(
        name="HOKA Running",
        url="https://www.hoka.com/en/us/running-shoes/",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        tags=("brand", "direct"),
        notes="Direct brand source for performance running shoes.",
    ),
    SourceSeed(
        name="Brooks Running",
        url="https://www.brooksrunning.com/en_us/mens-road-running-shoes/",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
        tags=("brand", "direct"),
        notes="Direct brand source focused on road shoes.",
    ),
    SourceSeed(
        name="Saucony Running",
        url="https://www.saucony.com/en/running-shoes/",
        kind=SourceKind.BRAND,
        category=GearCategory.RUNNING_SHOE,
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


def get_sources(category: GearCategory) -> List[SourceSeed]:
    return list(SEEDS_BY_CATEGORY.get(category, []))
