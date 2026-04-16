import unittest

from gear_miner.live_search import LiveWebDiscovery, parse_search_results
from gear_miner.models import GearCategory


SEARCH_HTML = """
<html>
  <body>
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.brooksrunning.com%2Fen_us%2Fghost-16%2F">
      Brooks Ghost 16 Running Shoes
    </a>
    <a data-testid="result-title-a" href="https://www.runningwarehouse.com/Brooks_Ghost_16/descpage-BG16.html">
      Running Warehouse Brooks Ghost 16
    </a>
    <a class="result__a" href="https://duckduckgo.com/?q=brooks">Ignored Search Engine Link</a>
  </body>
</html>
"""


class LiveWebDiscoveryTest(unittest.TestCase):
    def test_parse_search_results_normalizes_duckduckgo_redirects(self) -> None:
        results = parse_search_results(SEARCH_HTML)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].url, "https://www.brooksrunning.com/en_us/ghost-16/")
        self.assertEqual(results[1].url, "https://www.runningwarehouse.com/Brooks_Ghost_16/descpage-BG16.html")

    def test_discover_sources_collects_results_and_errors(self) -> None:
        calls = []

        def fetch_search_html(url: str) -> str:
            calls.append(url)
            if len(calls) == 2:
                raise RuntimeError("temporary search failure")
            return SEARCH_HTML

        progress_updates = []
        discovery = LiveWebDiscovery(fetch_search_html=fetch_search_html)
        report = discovery.discover_sources(
            brand="Brooks",
            category=GearCategory.RUNNING_SHOE,
            limit=3,
            progress_callback=lambda current, total, label: progress_updates.append((current, total, label)),
        )

        self.assertEqual(report.queries_attempted, 3)
        self.assertEqual(len(report.sources), 2)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("temporary search failure", report.errors[0])
        self.assertTrue(progress_updates)
        self.assertEqual(progress_updates[-1][2], "Live search discovery complete")


if __name__ == "__main__":
    unittest.main()
