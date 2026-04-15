from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Callable, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import HistoricalCapture, SourceSeed


WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
WAYBACK_ARCHIVE_BASE = "https://web.archive.org/web"
WAYBACK_HEADERS = {
    "User-Agent": "GearMinerBot/0.1 (+https://example.com/gear-miner)",
    "Accept": "application/json",
}


FetchJson = Callable[[str], object]


def default_fetch_json(url: str, timeout_seconds: int = 20) -> object:
    request = Request(url, headers=WAYBACK_HEADERS)
    with urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset, errors="replace"))


class WaybackCaptureIndex:
    def __init__(self, fetch_json: Optional[FetchJson] = None) -> None:
        self.fetch_json = fetch_json or default_fetch_json

    def list_captures(
        self,
        seed: SourceSeed,
        start_year: int,
        end_year: int,
    ) -> List[HistoricalCapture]:
        captures_by_year: Dict[int, HistoricalCapture] = {}
        for row in self._query_rows(seed.url, start_year=start_year, end_year=end_year):
            timestamp = str(row.get("timestamp", "")).strip()
            original_url = str(row.get("original", "")).strip() or seed.url
            if len(timestamp) < 4 or not timestamp[:4].isdigit():
                continue
            year = int(timestamp[:4])
            captures_by_year[year] = HistoricalCapture(
                timestamp=timestamp,
                original_url=original_url,
                archived_url=build_archived_url(timestamp, original_url),
            )

        captures = [captures_by_year[year] for year in sorted(captures_by_year)]
        current_year = datetime.now(timezone.utc).year
        if end_year >= current_year and current_year not in captures_by_year:
            captures.append(
                HistoricalCapture(
                    timestamp="live",
                    original_url=seed.url,
                    archived_url=seed.url,
                )
            )
        return captures

    def _query_rows(self, source_url: str, start_year: int, end_year: int) -> List[Dict[str, str]]:
        params = urlencode(
            [
                ("url", source_url),
                ("from", str(start_year)),
                ("to", str(end_year)),
                ("output", "json"),
                ("fl", "timestamp,original,statuscode"),
                ("filter", "statuscode:200"),
            ],
            doseq=True,
        )
        payload = self.fetch_json(f"{WAYBACK_CDX_URL}?{params}")
        if not isinstance(payload, list) or not payload:
            return []

        header = payload[0]
        if not isinstance(header, list):
            return []

        rows: List[Dict[str, str]] = []
        for raw_row in payload[1:]:
            if not isinstance(raw_row, list):
                continue
            row = {str(key): str(value) for key, value in zip(header, raw_row)}
            rows.append(row)
        return rows


def build_archived_url(timestamp: str, original_url: str) -> str:
    return f"{WAYBACK_ARCHIVE_BASE}/{timestamp}id_/{original_url}"
