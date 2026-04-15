from pathlib import Path
import tempfile
import time
import unittest

from gear_miner.models import HistoricalCapture
from gear_miner.pipeline import GearMinerAgent
from gear_miner.ui import RunManager, RunStatus, render_dashboard_page


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "running_vendor_page.html"


class FakeCaptureIndex:
    def list_captures(self, seed, start_year: int, end_year: int):
        return [
            HistoricalCapture(
                timestamp="20201201000000",
                original_url=seed.url,
                archived_url=seed.url,
            ),
            HistoricalCapture(
                timestamp="20231201000000",
                original_url=seed.url,
                archived_url=seed.url,
            ),
        ]


class GearMinerUiTest(unittest.TestCase):
    def test_run_manager_creates_excel_export_and_snapshot(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")

        def fetch_html(_: str) -> str:
            return html

        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = RunManager(
                data_dir=Path(tmp_dir),
                agent_factory=lambda: GearMinerAgent(
                    fetch_html=fetch_html,
                    capture_index=FakeCaptureIndex(),
                ),
            )
            run = manager.submit_run("Brooks", "Running shoes", "excel")
            final_run = self._wait_for_run(manager, run.run_id)

            self.assertEqual(final_run["status"], RunStatus.SUCCEEDED.value)
            self.assertTrue(final_run["export_path"].endswith(".xlsx"))
            self.assertTrue(Path(final_run["export_path"]).exists())
            self.assertTrue(Path(final_run["snapshot_path"]).exists())
            self.assertGreaterEqual(final_run["summary"]["products"], 1)

    def test_dashboard_page_contains_required_prompts(self) -> None:
        page = render_dashboard_page([])

        self.assertIn("Step 1: Brand", page)
        self.assertIn("Step 2: Product category", page)
        self.assertIn("Run Gear Miner", page)
        self.assertIn("2020 to present", page)

    def _wait_for_run(self, manager: RunManager, run_id: str) -> dict:
        deadline = time.time() + 5
        while time.time() < deadline:
            runs = {run["run_id"]: run for run in manager.list_runs()}
            run = runs[run_id]
            if run["status"] in {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value}:
                return run
            time.sleep(0.05)
        self.fail(f"Run {run_id} did not finish before timeout.")


if __name__ == "__main__":
    unittest.main()
