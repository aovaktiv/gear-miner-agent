from pathlib import Path
import tempfile
import unittest
import zipfile

from gear_miner.exporters import write_products_export
from gear_miner.models import ExportFormat, GearCategory, ProductCandidate, SourceKind


def build_product() -> ProductCandidate:
    return ProductCandidate(
        source_name="Nike Running",
        source_kind=SourceKind.BRAND,
        source_url="https://www.nike.com/running",
        product_url="https://www.nike.com/running/pegasus",
        category=GearCategory.RUNNING_SHOE,
        name="Nike Pegasus 41",
        brand="Nike",
        model="Pegasus 41",
        sku="PEG-41",
        price=140.0,
        currency="USD",
        product_type="Daily trainer",
        photo_url="https://example.com/images/nike-pegasus-41.png",
        photo_format="png",
        photo_path="/tmp/nike-pegasus-41.png",
        metadata={"color": "Blue"},
    )


class ProductExportTest(unittest.TestCase):
    def test_writes_csv_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "products.csv"
            write_products_export(path, [build_product()], ExportFormat.CSV)

            content = path.read_text(encoding="utf-8")
            self.assertIn("Brand,Product Name,Photo File", content)
            self.assertIn("Nike Pegasus 41", content)
            self.assertIn("/tmp/nike-pegasus-41.png", content)

    def test_writes_excel_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "products.xlsx"
            write_products_export(path, [build_product()], ExportFormat.EXCEL)

            with zipfile.ZipFile(path) as workbook:
                sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

            self.assertIn("Nike Pegasus 41", sheet_xml)
            self.assertIn("Brand", sheet_xml)
            self.assertIn("Product Name", sheet_xml)
            self.assertIn("Photo File", sheet_xml)
            self.assertIn("/tmp/nike-pegasus-41.png", sheet_xml)


if __name__ == "__main__":
    unittest.main()
