import unittest
from unittest.mock import patch

from gear_miner.cli import build_parser, resolve_brand, resolve_category
from gear_miner.models import GearCategory


class GearMinerCliTest(unittest.TestCase):
    def test_prompt_flow_uses_requested_step_labels(self) -> None:
        parser = build_parser()

        with patch("builtins.input", side_effect=["Nike", "Running shoes"]) as fake_input:
            brand = resolve_brand(None, prompt_if_missing=True)
            category = resolve_category(None, parser=parser, prompt_if_missing=True)

        self.assertEqual(brand, "Nike")
        self.assertEqual(category, GearCategory.RUNNING_SHOE)
        self.assertEqual(fake_input.call_args_list[0].args[0], "Step 1: Enter brand name: ")
        self.assertEqual(fake_input.call_args_list[1].args[0], "Step 2: Enter product category: ")


if __name__ == "__main__":
    unittest.main()
