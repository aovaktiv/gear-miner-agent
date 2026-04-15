from pathlib import Path
import tempfile
import threading
import time
import unittest

from gear_miner.models import HistoricalCapture
from gear_miner.photos import ProductPhotoStore
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


def fake_photo_store() -> ProductPhotoStore:
    return ProductPhotoStore(fetch_photo=lambda _: (b"png-bytes", "image/png"))


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
                photo_store=fake_photo_store(),
            )
            run = manager.submit_run("Brooks", "Running shoes", "excel")
            final_run = self._wait_for_run(manager, run.run_id)

            self.assertEqual(final_run["status"], RunStatus.SUCCEEDED.value)
            self.assertTrue(final_run["export_path"].endswith(".xlsx"))
            self.assertTrue(Path(final_run["export_path"]).exists())
            self.assertTrue(Path(final_run["snapshot_path"]).exists())
            self.assertGreaterEqual(final_run["summary"]["products"], 1)
            self.assertGreaterEqual(final_run["summary"]["photos_saved"], 1)

    def test_dashboard_page_contains_required_prompts(self) -> None:
        page = render_dashboard_page([])

        self.assertIn("Step 1: Brand", page)
        self.assertIn("Step 2: Product category", page)
        self.assertIn("Run Gear Miner", page)
        self.assertIn("2020 to present", page)
        self.assertIn("Kill Last Job", page)
        self.assertIn("Clear for New Search", page)

    def test_reset_latest_run_clears_completed_run(self) -> None:
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
                photo_store=fake_photo_store(),
            )
            run = manager.submit_run("Brooks", "Running shoes", "csv")
            final_run = self._wait_for_run(manager, run.run_id)
            self.assertTrue(Path(final_run["export_path"]).exists())
            self.assertTrue(Path(final_run["snapshot_path"]).exists())
            self.assertTrue((Path(tmp_dir) / "photos" / run.run_id).exists())

            result = manager.reset_latest_run()

            self.assertEqual(result["action"], "cleared")
            self.assertEqual(result["run"]["run_id"], run.run_id)
            self.assertEqual(manager.list_runs(), [])
            self.assertFalse(Path(result["run"]["export_path"]).exists())
            self.assertFalse(Path(result["run"]["snapshot_path"]).exists())
            self.assertFalse((Path(tmp_dir) / "photos" / run.run_id).exists())

    def test_reset_latest_run_requests_cancellation_for_active_run(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")
        release_fetch = threading.Event()

        def fetch_html(_: str) -> str:
            release_fetch.wait(timeout=1)
            return html

        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = RunManager(
                data_dir=Path(tmp_dir),
                agent_factory=lambda: GearMinerAgent(
                    fetch_html=fetch_html,
                    capture_index=FakeCaptureIndex(),
                ),
                photo_store=fake_photo_store(),
            )
            run = manager.submit_run("Brooks", "Running shoes", "csv")
            self._wait_for_status(manager, run.run_id, {RunStatus.RUNNING.value})

            result = manager.reset_latest_run()
            self.assertEqual(result["action"], "cancel_requested")

            release_fetch.set()
            final_run = self._wait_for_status(manager, run.run_id, {RunStatus.CANCELLED.value})
            self.assertEqual(final_run["error"], "Run cancelled by user.")

    def _wait_for_run(self, manager: RunManager, run_id: str) -> dict:
        return self._wait_for_status(manager, run_id, {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value})

    def _wait_for_status(self, manager: RunManager, run_id: str, statuses: set[str]) -> dict:
        deadline = time.time() + 5
        while time.time() < deadline:
            runs = {run["run_id"]: run for run in manager.list_runs()}
            run = runs[run_id]
            if run["status"] in statuses:
                return run
            time.sleep(0.05)
        self.fail(f"Run {run_id} did not reach statuses {statuses} before timeout.")


if __name__ == "__main__":
    unittest.main()
