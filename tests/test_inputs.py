import unittest

from gear_miner.models import GearCategory
from gear_miner.seeds import get_sources


class GearMinerInputsTest(unittest.TestCase):
    def test_category_parser_accepts_human_friendly_text(self) -> None:
        self.assertEqual(GearCategory.parse("Running shoes"), GearCategory.RUNNING_SHOE)
        self.assertEqual(GearCategory.parse("running-shoe"), GearCategory.RUNNING_SHOE)

    def test_get_sources_keeps_matching_brand_and_shared_sources(self) -> None:
        sources = get_sources(GearCategory.RUNNING_SHOE, brand="Nike")
        source_names = [source.name for source in sources]

        self.assertEqual(
            source_names,
            ["Nike Running", "Running Warehouse", "REI Running Shoes"],
        )

    def test_get_sources_falls_back_to_shared_sources_for_unknown_brand(self) -> None:
        sources = get_sources(GearCategory.RUNNING_SHOE, brand="Tracksmith")

        self.assertEqual([source.kind.value for source in sources], ["retailer", "retailer"])


if __name__ == "__main__":
    unittest.main()
