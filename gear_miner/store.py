from __future__ import annotations

import json
from pathlib import Path

from .models import MineReport


def write_snapshot(path: Path, report: MineReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    path.write_text(payload + "\n", encoding="utf-8")
