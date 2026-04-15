import unittest

from gear_miner.history import WaybackCaptureIndex, build_archived_url
from gear_miner.models import SourceKind, SourceSeed, GearCategory


class WaybackCaptureIndexTest(unittest.TestCase):
    def test_selects_latest_capture_per_year_and_adds_live_current_year(self) -> None:
        payload = [
            ["timestamp", "original", "statuscode"],
            ["20200101000000", "https://example.com/running", "200"],
            ["20201001000000", "https://example.com/running", "200"],
            ["20210305000000", "https://example.com/running", "200"],
        ]
        index = WaybackCaptureIndex(fetch_json=lambda _: payload)
        seed = SourceSeed(
            name="Fixture Running",
            url="https://example.com/running",
            kind=SourceKind.BRAND,
            category=GearCategory.RUNNING_SHOE,
        )

        captures = index.list_captures(seed, start_year=2020, end_year=2026)

        self.assertEqual(captures[0].timestamp, "20201001000000")
        self.assertEqual(captures[1].timestamp, "20210305000000")
        self.assertEqual(captures[-1].timestamp, "live")
        self.assertEqual(captures[-1].archived_url, "https://example.com/running")

    def test_builds_archived_url(self) -> None:
        self.assertEqual(
            build_archived_url("20240102030405", "https://example.com/running"),
            "https://web.archive.org/web/20240102030405id_/https://example.com/running",
        )


if __name__ == "__main__":
    unittest.main()
