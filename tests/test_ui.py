from pathlib import Path
import tempfile
import threading
import time
import unittest

from gear_miner.live_search import DiscoveryReport
from gear_miner.models import GearCategory, SourceKind, SourceSeed
from gear_miner.photos import ProductPhotoStore
from gear_miner.pipeline import GearMinerAgent
from gear_miner.ui import RunManager, RunStatus, render_dashboard_page


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "running_vendor_page.html"


class FakeLiveDiscovery:
    def __init__(self, sources):
        self.sources = list(sources)

    def discover_sources(
        self,
        brand: str,
        category: GearCategory,
        limit: int = 20,
        allow_domains=(),
        block_domains=(),
        progress_callback=None,
    ):
        if progress_callback:
            progress_callback(0, 3, f'Searching live web: "{brand}" "{category.display_name}"')
            progress_callback(3, 3, "Live search discovery complete")
        return DiscoveryReport(
            sources=self.sources[:limit],
            errors=[],
            queries_attempted=3,
        )


def fake_photo_store() -> ProductPhotoStore:
    return ProductPhotoStore(fetch_photo=lambda _: (b"png-bytes", "image/png"))


def fake_live_sources() -> list[SourceSeed]:
    return [
        SourceSeed(
            name="Live Brooks Result",
            url="https://example.com/live-brooks",
            kind=SourceKind.BRAND,
            category=GearCategory.RUNNING_SHOE,
            brand="Brooks",
            tags=("live-search",),
        ),
        SourceSeed(
            name="Live Retailer Result",
            url="https://example.com/live-retailer",
            kind=SourceKind.RETAILER,
            category=GearCategory.RUNNING_SHOE,
            tags=("live-search",),
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
                    live_discovery=FakeLiveDiscovery(fake_live_sources()),
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
        self.assertIn("Allow domains", page)
        self.assertIn("Block domains", page)
        self.assertIn("Search History", page)
        self.assertIn("Run Gear Miner", page)
        self.assertIn("live web search", page)
        self.assertIn("Terminate Selected Search", page)
        self.assertIn("Clear Selected Search", page)
        self.assertIn("progress-fill", page)

    def test_reset_latest_run_clears_completed_run(self) -> None:
        html = FIXTURE.read_text(encoding="utf-8")

        def fetch_html(_: str) -> str:
            return html

        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = RunManager(
                data_dir=Path(tmp_dir),
                agent_factory=lambda: GearMinerAgent(
                    fetch_html=fetch_html,
                    live_discovery=FakeLiveDiscovery(fake_live_sources()),
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
                    live_discovery=FakeLiveDiscovery(fake_live_sources()),
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

    def test_active_run_exposes_progress_updates(self) -> None:
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
                    live_discovery=FakeLiveDiscovery(fake_live_sources()),
                ),
                photo_store=fake_photo_store(),
            )
            run = manager.submit_run("Brooks", "Running shoes", "csv")
            running = self._wait_for_status(manager, run.run_id, {RunStatus.RUNNING.value})

            self.assertGreater(running["progress_current"], 0)
            self.assertEqual(running["progress_total"], 100)
            self.assertTrue(running["progress_label"])

            release_fetch.set()
            self._wait_for_run(manager, run.run_id)

    def test_manage_run_can_cancel_selected_active_run(self) -> None:
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
                    live_discovery=FakeLiveDiscovery(fake_live_sources()),
                ),
                photo_store=fake_photo_store(),
            )
            first = manager.submit_run("Brooks", "Running shoes", "csv")
            second = manager.submit_run("Brooks", "Running shoes", "csv")
            self._wait_for_status(manager, first.run_id, {RunStatus.RUNNING.value})
            self._wait_for_status(manager, second.run_id, {RunStatus.RUNNING.value, RunStatus.QUEUED.value})

            result = manager.manage_run(first.run_id)
            self.assertEqual(result["action"], "cancel_requested")
            self.assertEqual(result["run"]["run_id"], first.run_id)

            release_fetch.set()
            cancelled = self._wait_for_status(manager, first.run_id, {RunStatus.CANCELLED.value})
            completed = self._wait_for_status(manager, second.run_id, {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value})

            self.assertEqual(cancelled["error"], "Run cancelled by user.")
            self.assertEqual(completed["status"], RunStatus.SUCCEEDED.value)

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
