from pathlib import Path
import json
import tempfile
import unittest

from gear_miner.models import GearCategory, SourceKind, SourceSeed
from gear_miner.pipeline import GearMinerAgent


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "running_vendor_page.html"


class GearMinerAgentTest(unittest.TestCase):
    def test_pipeline_writes_snapshot_and_tracks_failures(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        payloads = {
            "https://example.com/running": html,
        }

        def fetch_html(url: str) -> str:
            if url not in payloads:
                raise RuntimeError("source unavailable")
            return payloads[url]

        seeds = [
            SourceSeed(
                name="Fixture Running",
                url="https://example.com/running",
                kind=SourceKind.BRAND,
                category=GearCategory.RUNNING_SHOE,
            ),
            SourceSeed(
                name="Broken Source",
                url="https://example.com/broken",
                kind=SourceKind.RETAILER,
                category=GearCategory.RUNNING_SHOE,
            ),
        ]

        agent = GearMinerAgent(fetch_html=fetch_html)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "snapshot.json"
            report = agent.mine_sources(
                seeds=seeds,
                category=GearCategory.RUNNING_SHOE,
                output_path=output,
            )

            self.assertEqual(report.attempted_sources, 2)
            self.assertEqual(report.succeeded_sources, 1)
            self.assertEqual(report.failed_sources, 1)
            self.assertEqual(len(report.products), 2)
            self.assertEqual(report.unique_models, 2)

            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["summary"]["products"], 2)
            self.assertEqual(snapshot["summary"]["failed_sources"], 1)

    def test_pipeline_filters_products_to_requested_brand(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")

        def fetch_html(_: str) -> str:
            return html

        seeds = [
            SourceSeed(
                name="Fixture Running",
                url="https://example.com/running",
                kind=SourceKind.RETAILER,
                category=GearCategory.RUNNING_SHOE,
            ),
        ]

        agent = GearMinerAgent(fetch_html=fetch_html)
        report = agent.mine_sources(
            seeds=seeds,
            category=GearCategory.RUNNING_SHOE,
            requested_brand="Brooks",
        )

        self.assertEqual(report.requested_brand, "Brooks")
        self.assertEqual(len(report.products), 1)
        self.assertEqual(report.products[0].brand, "Brooks")


if __name__ == "__main__":
    unittest.main()
