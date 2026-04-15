from pathlib import Path
import json
import tempfile
import unittest

from gear_miner.models import GearCategory, HistoricalCapture, SourceKind, SourceSeed
from gear_miner.pipeline import GearMinerAgent


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "running_vendor_page.html"


class FakeCaptureIndex:
    def __init__(self, captures_by_url):
        self.captures_by_url = captures_by_url

    def list_captures(self, seed: SourceSeed, start_year: int, end_year: int):
        return list(self.captures_by_url.get(seed.url, []))


class GearMinerAgentTest(unittest.TestCase):
    def test_pipeline_writes_snapshot_and_tracks_failures(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        payloads = {
            "https://web.archive.org/web/20201201000000id_/https://example.com/running": html,
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

        agent = GearMinerAgent(
            fetch_html=fetch_html,
            capture_index=FakeCaptureIndex(
                {
                    "https://example.com/running": [
                        HistoricalCapture(
                            timestamp="20201201000000",
                            original_url="https://example.com/running",
                            archived_url="https://web.archive.org/web/20201201000000id_/https://example.com/running",
                        )
                    ],
                    "https://example.com/broken": [
                        HistoricalCapture(
                            timestamp="20211201000000",
                            original_url="https://example.com/broken",
                            archived_url="https://web.archive.org/web/20211201000000id_/https://example.com/broken",
                        )
                    ],
                }
            ),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "snapshot.json"
            report = agent.mine_sources(
                seeds=seeds,
                category=GearCategory.RUNNING_SHOE,
                output_path=output,
                search_start_year=2020,
                search_end_year=2024,
            )

            self.assertEqual(report.attempted_sources, 2)
            self.assertEqual(report.succeeded_sources, 1)
            self.assertEqual(report.failed_sources, 1)
            self.assertEqual(len(report.products), 2)
            self.assertEqual(report.unique_models, 2)
            self.assertEqual(report.search_start_year, 2020)
            self.assertEqual(report.search_end_year, 2024)

            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["summary"]["products"], 2)
            self.assertEqual(snapshot["summary"]["failed_sources"], 1)
            self.assertEqual(snapshot["search_start_year"], 2020)

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

        agent = GearMinerAgent(
            fetch_html=fetch_html,
            capture_index=FakeCaptureIndex(
                {
                    "https://example.com/running": [
                        HistoricalCapture(
                            timestamp="20221201000000",
                            original_url="https://example.com/running",
                            archived_url="https://web.archive.org/web/20221201000000id_/https://example.com/running",
                        ),
                        HistoricalCapture(
                            timestamp="20231201000000",
                            original_url="https://example.com/running",
                            archived_url="https://web.archive.org/web/20231201000000id_/https://example.com/running",
                        ),
                    ]
                }
            ),
        )
        report = agent.mine_sources(
            seeds=seeds,
            category=GearCategory.RUNNING_SHOE,
            requested_brand="Brooks",
            search_start_year=2020,
            search_end_year=2024,
        )

        self.assertEqual(report.requested_brand, "Brooks")
        self.assertEqual(len(report.products), 1)
        self.assertEqual(report.products[0].brand, "Brooks")
        self.assertEqual(report.outcomes[0].capture_count, 2)
        self.assertEqual(report.outcomes[0].extracted_count, 2)


if __name__ == "__main__":
    unittest.main()
