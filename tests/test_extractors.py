from pathlib import Path
import unittest

from gear_miner.extractors import JsonLdProductExtractor
from gear_miner.models import GearCategory, SourceKind, SourceSeed


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "running_vendor_page.html"


class JsonLdProductExtractorTest(unittest.TestCase):
    def test_extracts_products_from_json_ld(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        seed = SourceSeed(
            name="Fixture Running",
            url="https://example.com/running",
            kind=SourceKind.BRAND,
            category=GearCategory.RUNNING_SHOE,
        )

        products = JsonLdProductExtractor().extract(html, seed)

        self.assertEqual(len(products), 2)

        ghost = products[0]
        self.assertEqual(ghost.brand, "Brooks")
        self.assertEqual(ghost.model, "Ghost 16")
        self.assertEqual(ghost.price, 140.0)
        self.assertEqual(ghost.currency, "USD")
        self.assertEqual(ghost.photo_url, "https://example.com/images/brooks-ghost-16.jpg")
        self.assertEqual(ghost.photo_format, "jpg")

        clifton = products[1]
        self.assertEqual(clifton.brand, "HOKA")
        self.assertEqual(clifton.model, "Clifton 10")
        self.assertEqual(clifton.price, 145.0)
        self.assertIsNone(clifton.photo_url)


if __name__ == "__main__":
    unittest.main()
