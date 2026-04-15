from pathlib import Path
import tempfile
import unittest

from gear_miner.models import GearCategory, ProductCandidate, SourceKind
from gear_miner.photos import ProductPhotoStore


class ProductPhotoStoreTest(unittest.TestCase):
    def test_saves_supported_photo_file(self) -> None:
        product = ProductCandidate(
            source_name="Nike Running",
            source_kind=SourceKind.BRAND,
            source_url="https://example.com/source",
            product_url="https://example.com/product",
            category=GearCategory.RUNNING_SHOE,
            name="Nike Pegasus 41",
            brand="Nike",
            model="Pegasus 41",
            photo_url="https://example.com/images/nike-pegasus-41.jpg",
            photo_format="jpg",
        )
        store = ProductPhotoStore(fetch_photo=lambda _: (b"jpg-bytes", "image/jpeg"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = store.save_product_photos([product], Path(tmp_dir))

            self.assertEqual(result.saved_count, 1)
            self.assertTrue(product.photo_path.endswith(".jpg"))
            self.assertTrue(Path(product.photo_path).exists())

    def test_skips_unsupported_photo_format(self) -> None:
        product = ProductCandidate(
            source_name="Nike Running",
            source_kind=SourceKind.BRAND,
            source_url="https://example.com/source",
            product_url="https://example.com/product",
            category=GearCategory.RUNNING_SHOE,
            name="Nike Pegasus 41",
            brand="Nike",
            model="Pegasus 41",
            photo_url="https://example.com/images/nike-pegasus-41.webp",
        )
        store = ProductPhotoStore(fetch_photo=lambda _: (b"webp", "image/webp"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = store.save_product_photos([product], Path(tmp_dir))

            self.assertEqual(result.saved_count, 0)
            self.assertEqual(result.skipped_count, 1)
            self.assertIsNone(product.photo_path)


if __name__ == "__main__":
    unittest.main()
