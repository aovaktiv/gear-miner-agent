from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import shutil
import threading
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs
from uuid import uuid4

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .domains import parse_domain_list
from .exporters import write_products_export
from .models import ExportFormat, GearCategory, slugify
from .photos import ProductPhotoStore
from .pipeline import GearMinerAgent, MiningCancelled


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().replace(microsecond=0).isoformat()


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunCancelled(Exception):
    pass


@dataclass
class ManagedRun:
    run_id: str
    brand: str
    category_input: str
    category: str
    allow_domains: List[str]
    block_domains: List[str]
    export_format: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    snapshot_path: Optional[str] = None
    export_path: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    product_preview: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 100
    progress_label: str = "Queued"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "brand": self.brand,
            "category_input": self.category_input,
            "category": self.category,
            "allow_domains": self.allow_domains,
            "block_domains": self.block_domains,
            "export_format": self.export_format,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "snapshot_path": self.snapshot_path,
            "export_path": self.export_path,
            "summary": self.summary,
            "outcomes": self.outcomes,
            "product_preview": self.product_preview,
            "warnings": self.warnings,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "progress_label": self.progress_label,
            "error": self.error,
        }


class RunManager:
    def __init__(
        self,
        data_dir: Path,
        agent_factory: Optional[Callable[[], GearMinerAgent]] = None,
        photo_store: Optional[ProductPhotoStore] = None,
    ) -> None:
        self.data_dir = data_dir
        self.state_path = data_dir / "ui_runs.json"
        self.snapshots_dir = data_dir / "snapshots"
        self.exports_dir = data_dir / "exports"
        self.photos_dir = data_dir / "photos"
        self.agent_factory = agent_factory or GearMinerAgent
        self.photo_store = photo_store or ProductPhotoStore()
        self._lock = threading.Lock()
        self._runs: Dict[str, ManagedRun] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._load()

    def submit_run(
        self,
        brand: str,
        category_input: str,
        export_format_input: str,
        allow_domains_input: str = "",
        block_domains_input: str = "",
    ) -> ManagedRun:
        brand_value = brand.strip()
        if not brand_value:
            raise ValueError("Brand is required.")

        category = GearCategory.parse(category_input)
        export_format = ExportFormat.parse(export_format_input)
        allow_domains = list(parse_domain_list(allow_domains_input))
        block_domains = list(parse_domain_list(block_domains_input))
        run = ManagedRun(
            run_id=uuid4().hex[:12],
            brand=brand_value,
            category_input=category_input.strip(),
            category=category.value,
            allow_domains=allow_domains,
            block_domains=block_domains,
            export_format=export_format.value,
            status=RunStatus.QUEUED.value,
            created_at=utc_now_iso(),
        )

        with self._lock:
            self._runs[run.run_id] = run
            self._cancel_events[run.run_id] = threading.Event()
            self._save_locked()

        thread = threading.Thread(target=self._execute_run, args=(run.run_id,), daemon=True)
        thread.start()
        return run

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            runs = [run.to_dict() for run in self._runs.values()]
        return sorted(runs, key=lambda run: run["created_at"], reverse=True)

    def reset_latest_run(self) -> Dict[str, Any]:
        with self._lock:
            latest_run = self._latest_run_locked()
            if latest_run is None:
                raise ValueError("There is no run to reset.")

            run_id = latest_run.run_id

        return self.manage_run(run_id)

    def manage_run(self, run_id: str) -> Dict[str, Any]:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise ValueError(f"Unknown run '{run_id}'.")

            if run.status in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
                cancel_event = self._cancel_events.setdefault(run.run_id, threading.Event())
                cancel_event.set()
                self._save_locked()
                return {
                    "action": "cancel_requested",
                    "run": run.to_dict(),
                }

            removed = self._runs.pop(run.run_id)
            self._cancel_events.pop(run.run_id, None)
            self._delete_run_artifacts(removed)
            self._save_locked()
            return {
                "action": "cleared",
                "run": removed.to_dict(),
            }

    def resolve_artifact(self, run_id: str, artifact: str) -> tuple[Path, str, str]:
        with self._lock:
            run = self._runs.get(run_id)

        if run is None:
            raise KeyError(f"Unknown run '{run_id}'.")

        if artifact == "output" and run.export_path:
            path = Path(run.export_path)
            export_format = ExportFormat.parse(run.export_format)
            filename = path.name
            return path, export_format.content_type, filename

        if artifact == "snapshot" and run.snapshot_path:
            path = Path(run.snapshot_path)
            return path, "application/json; charset=utf-8", path.name

        raise FileNotFoundError(f"Run '{run_id}' does not have a {artifact} artifact yet.")

    def resolve_photo(self, run_id: str, filename: str) -> tuple[Path, str]:
        photo_path = (self.photos_dir / run_id / filename).resolve()
        photos_root = (self.photos_dir / run_id).resolve()
        if not str(photo_path).startswith(str(photos_root)) or not photo_path.exists():
            raise FileNotFoundError(f"Photo '{filename}' not found for run '{run_id}'.")

        content_type = "image/png" if photo_path.suffix.lower() == ".png" else "image/jpeg"
        return photo_path, content_type

    def _execute_run(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run.status = RunStatus.RUNNING.value
            run.started_at = utc_now_iso()
            run.progress_current = 3
            run.progress_total = 100
            run.progress_label = "Starting live web search"
            self._save_locked()

        try:
            self._raise_if_cancelled(run_id)
            category = GearCategory(run.category)
            export_format = ExportFormat.parse(run.export_format)
            base_name = self._build_base_name(run.run_id, run.brand, category)
            snapshot_path = self.snapshots_dir / f"{base_name}.json"
            export_path = self.exports_dir / f"{base_name}.{export_format.extension}"
            photo_dir = self.photos_dir / run.run_id

            agent = self.agent_factory()
            agent.should_cancel = lambda run_id=run_id: self._cancel_events.get(run_id, threading.Event()).is_set()
            agent.progress_callback = lambda current, total, label, run_id=run_id: self._update_progress(
                run_id,
                current,
                total,
                label,
            )
            report = agent.mine_category(
                category=category,
                brand=run.brand,
                output_path=snapshot_path,
                allow_domains=run.allow_domains,
                block_domains=run.block_domains,
            )
            self._raise_if_cancelled(run_id)
            self._update_progress(run_id, 82, 100, "Saving product photos")
            photo_result = self.photo_store.save_product_photos(
                report.products,
                photo_dir,
                progress_callback=lambda current, total, label, run_id=run_id: self._update_weighted_progress(
                    run_id,
                    start=82,
                    end=96,
                    current=current,
                    total=total,
                    label=label,
                ),
            )
            self._raise_if_cancelled(run_id)
            self._update_progress(run_id, 97, 100, f"Writing {export_format.label} export")
            write_products_export(export_path, report.products, export_format)
            self._raise_if_cancelled(run_id)

            payload = report.to_dict()
            with self._lock:
                run.status = RunStatus.SUCCEEDED.value
                run.finished_at = utc_now_iso()
                run.snapshot_path = str(snapshot_path.resolve())
                run.export_path = str(export_path.resolve())
                run.summary = payload["summary"]
                run.outcomes = payload["outcomes"]
                run.warnings = payload.get("warnings", []) + list(photo_result.errors)
                run.product_preview = [
                    {
                        "name": product["name"],
                        "brand": product["brand"],
                        "model": product["model"],
                        "price": product["price"],
                        "currency": product["currency"],
                        "photo_path": product.get("photo_path"),
                        "photo_name": Path(product["photo_path"]).name if product.get("photo_path") else None,
                        "product_url": product["product_url"],
                    }
                    for product in payload["products"][:10]
                ]
                run.summary["photos_saved"] = photo_result.saved_count
                run.summary["photos_skipped"] = photo_result.skipped_count
                run.summary["warning_count"] = len(run.warnings)
                run.progress_current = 100
                run.progress_total = 100
                run.progress_label = "Live search complete"
                self._save_locked()
        except (RunCancelled, MiningCancelled):
            with self._lock:
                run = self._runs.get(run_id)
                if run is None:
                    return
                run.status = RunStatus.CANCELLED.value
                run.finished_at = utc_now_iso()
                run.error = "Run cancelled by user."
                run.progress_label = "Run cancelled"
                self._save_locked()
        except Exception as exc:
            with self._lock:
                run = self._runs[run_id]
                run.status = RunStatus.FAILED.value
                run.finished_at = utc_now_iso()
                run.error = str(exc)
                run.progress_label = "Run failed"
                self._save_locked()

    def _build_base_name(self, run_id: str, brand: str, category: GearCategory) -> str:
        timestamp = utc_now().strftime("%Y%m%d-%H%M%S")
        return f"{slugify(brand)}-{slugify(category.display_name)}-{timestamp}-{run_id}"

    def _raise_if_cancelled(self, run_id: str) -> None:
        cancel_event = self._cancel_events.get(run_id)
        if cancel_event is not None and cancel_event.is_set():
            raise RunCancelled()

    def _latest_run_locked(self) -> Optional[ManagedRun]:
        if not self._runs:
            return None
        return max(self._runs.values(), key=lambda run: run.created_at)

    def _update_progress(self, run_id: str, current: int, total: int, label: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.progress_current = max(current, 0)
            run.progress_total = max(total, 1)
            run.progress_label = label
            self._save_locked()

    def _update_weighted_progress(
        self,
        run_id: str,
        start: int,
        end: int,
        current: int,
        total: int,
        label: str,
    ) -> None:
        if total <= 0:
            self._update_progress(run_id, end, 100, label)
            return

        bounded_current = min(max(current, 0), total)
        progress = start + int(((end - start) * bounded_current) / total)
        self._update_progress(run_id, progress, 100, label)

    def _delete_run_artifacts(self, run: ManagedRun) -> None:
        for raw_path in (run.snapshot_path, run.export_path):
            if raw_path:
                path = Path(raw_path)
                if path.exists():
                    path.unlink()

        run_photo_dir = self.photos_dir / run.run_id
        if run_photo_dir.exists():
            shutil.rmtree(run_photo_dir)

    def _load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            return

        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        runs = {}
        for item in payload.get("runs", []):
            run = ManagedRun(
                run_id=item["run_id"],
                brand=item["brand"],
                category_input=item.get("category_input", item["category"]),
                category=item["category"],
                allow_domains=item.get("allow_domains", []),
                block_domains=item.get("block_domains", []),
                export_format=item["export_format"],
                status=item["status"],
                created_at=item["created_at"],
                started_at=item.get("started_at"),
                finished_at=item.get("finished_at"),
                snapshot_path=item.get("snapshot_path"),
                export_path=item.get("export_path"),
                summary=item.get("summary", {}),
                outcomes=item.get("outcomes", []),
                product_preview=item.get("product_preview", []),
                warnings=item.get("warnings", []),
                progress_current=item.get("progress_current", 0),
                progress_total=item.get("progress_total", 100),
                progress_label=item.get("progress_label", "Queued"),
                error=item.get("error"),
            )
            runs[run.run_id] = run
            self._cancel_events[run.run_id] = threading.Event()
        self._runs = runs

    def _save_locked(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {"runs": [run.to_dict() for run in self._runs.values()]}
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: Optional[Path] = None,
    agent_factory: Optional[Callable[[], GearMinerAgent]] = None,
) -> ThreadingHTTPServer:
    manager = RunManager(data_dir=data_dir or Path("data/ui"), agent_factory=agent_factory)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._send_bytes(b"ok\n", "text/plain; charset=utf-8")
                return

            if self.path == "/":
                page = render_dashboard_page(manager.list_runs())
                self._send_bytes(page.encode("utf-8"), "text/html; charset=utf-8")
                return

            if self.path == "/api/runs":
                payload = json.dumps({"runs": manager.list_runs()}).encode("utf-8")
                self._send_bytes(payload, "application/json; charset=utf-8")
                return

            if self.path.startswith("/media/"):
                self._handle_media()
                return

            if self.path.startswith("/download/"):
                self._handle_download()
                return

            self.send_error(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/api/runs/last/reset":
                try:
                    payload = manager.reset_latest_run()
                    body = json.dumps(payload).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8", status=200)
                except ValueError as exc:
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8", status=400)
                return

            if self.path.startswith("/api/runs/") and self.path.endswith("/reset"):
                parts = self.path.strip("/").split("/")
                if len(parts) != 4:
                    self.send_error(404, "Not found")
                    return
                _, _, run_id, _ = parts
                try:
                    payload = manager.manage_run(run_id)
                    body = json.dumps(payload).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8", status=200)
                except ValueError as exc:
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self._send_bytes(body, "application/json; charset=utf-8", status=400)
                return

            if self.path != "/api/runs":
                self.send_error(404, "Not found")
                return

            try:
                payload = self._read_form_payload()
                run = manager.submit_run(
                    brand=payload.get("brand", ""),
                    category_input=payload.get("category", ""),
                    export_format_input=payload.get("export_format", ExportFormat.CSV.value),
                    allow_domains_input=payload.get("allow_domains", ""),
                    block_domains_input=payload.get("block_domains", ""),
                )
                body = json.dumps({"run": run.to_dict()}).encode("utf-8")
                self._send_bytes(body, "application/json; charset=utf-8", status=201)
            except ValueError as exc:
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self._send_bytes(body, "application/json; charset=utf-8", status=400)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_form_payload(self) -> Dict[str, str]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            parsed = parse_qs(raw, keep_blank_values=True)
            return {key: values[-1] for key, values in parsed.items()}

        def _handle_download(self) -> None:
            parts = self.path.strip("/").split("/")
            if len(parts) != 3:
                self.send_error(404, "Not found")
                return

            _, run_id, artifact = parts
            try:
                path, content_type, filename = manager.resolve_artifact(run_id, artifact)
            except KeyError:
                self.send_error(404, "Unknown run")
                return
            except FileNotFoundError:
                self.send_error(404, "Artifact not ready")
                return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(path.read_bytes())

        def _handle_media(self) -> None:
            parts = self.path.strip("/").split("/")
            if len(parts) != 3:
                self.send_error(404, "Not found")
                return

            _, run_id, filename = parts
            try:
                path, content_type = manager.resolve_photo(run_id, filename)
            except FileNotFoundError:
                self.send_error(404, "Photo not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            self.wfile.write(path.read_bytes())

        def _send_bytes(self, payload: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((host, port), Handler)
    setattr(server, "run_manager", manager)
    return server


def render_dashboard_page(runs: List[Dict[str, Any]]) -> str:
    initial_runs_json = json.dumps(runs)
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Gear Miner Control Room</title>
    <style>
      :root {{
        --bg: #f6f1e8;
        --ink: #14213d;
        --panel: rgba(255, 251, 245, 0.88);
        --line: rgba(20, 33, 61, 0.12);
        --accent: #ff6b35;
        --accent-2: #2a9d8f;
        --accent-3: #f4a261;
        --success: #177245;
        --danger: #a22c29;
        --shadow: 0 24px 60px rgba(20, 33, 61, 0.14);
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        min-height: 100vh;
        font-family: "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(255, 107, 53, 0.24), transparent 30%),
          radial-gradient(circle at top right, rgba(42, 157, 143, 0.18), transparent 28%),
          linear-gradient(180deg, #fff9f0 0%, var(--bg) 50%, #efe6d7 100%);
      }}

      body::before {{
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image:
          linear-gradient(rgba(20, 33, 61, 0.03) 1px, transparent 1px),
          linear-gradient(90deg, rgba(20, 33, 61, 0.03) 1px, transparent 1px);
        background-size: 22px 22px;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.3), transparent 80%);
      }}

      .shell {{
        width: min(1160px, calc(100% - 32px));
        margin: 32px auto 48px;
      }}

      .hero {{
        position: relative;
        overflow: hidden;
        padding: 28px;
        border-radius: 28px;
        background:
          linear-gradient(135deg, rgba(20, 33, 61, 0.96), rgba(32, 53, 89, 0.92)),
          linear-gradient(135deg, rgba(255, 107, 53, 0.25), rgba(42, 157, 143, 0.16));
        color: #fff7ef;
        box-shadow: var(--shadow);
      }}

      .hero::after {{
        content: "";
        position: absolute;
        width: 260px;
        height: 260px;
        right: -80px;
        top: -110px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 107, 53, 0.34), transparent 70%);
      }}

      .hero h1 {{
        margin: 0 0 10px;
        font-size: clamp(2rem, 4vw, 3.5rem);
        line-height: 0.95;
        letter-spacing: -0.04em;
      }}

      .hero p {{
        margin: 0;
        max-width: 58ch;
        color: rgba(255, 247, 239, 0.82);
        font-size: 1rem;
      }}

      .layout {{
        display: grid;
        grid-template-columns: minmax(320px, 400px) minmax(0, 1fr);
        gap: 22px;
        margin-top: 22px;
      }}

      .panel {{
        background: var(--panel);
        backdrop-filter: blur(12px);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: var(--shadow);
      }}

      .form-panel {{
        padding: 22px;
        position: sticky;
        top: 20px;
        align-self: start;
      }}

      .eyebrow {{
        display: inline-flex;
        margin-bottom: 14px;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(255, 107, 53, 0.12);
        color: var(--accent);
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}

      h2 {{
        margin: 0 0 10px;
        font-size: 1.4rem;
        letter-spacing: -0.03em;
      }}

      .subcopy {{
        margin: 0 0 18px;
        color: rgba(20, 33, 61, 0.72);
      }}

      .field {{
        margin-bottom: 16px;
      }}

      .field label {{
        display: block;
        margin-bottom: 8px;
        font-weight: 700;
      }}

      .field small {{
        display: block;
        color: rgba(20, 33, 61, 0.62);
        margin-top: 6px;
      }}

      input[type="text"] {{
        width: 100%;
        padding: 14px 16px;
        border-radius: 16px;
        border: 1px solid rgba(20, 33, 61, 0.12);
        background: rgba(255, 255, 255, 0.82);
        font: inherit;
        color: var(--ink);
      }}

      .format-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }}

      .format-option {{
        position: relative;
      }}

      .format-option input {{
        position: absolute;
        opacity: 0;
        pointer-events: none;
      }}

      .format-option span {{
        display: block;
        padding: 14px 12px;
        border-radius: 16px;
        border: 1px solid rgba(20, 33, 61, 0.12);
        background: rgba(255, 255, 255, 0.76);
        text-align: center;
        font-weight: 700;
        transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
      }}

      .format-option input:checked + span {{
        background: rgba(255, 107, 53, 0.14);
        border-color: rgba(255, 107, 53, 0.48);
        transform: translateY(-1px);
      }}

      button {{
        width: 100%;
        padding: 15px 18px;
        border: 0;
        border-radius: 16px;
        font: inherit;
        font-weight: 800;
        color: white;
        background: linear-gradient(135deg, var(--accent), #ff844f);
        cursor: pointer;
        box-shadow: 0 18px 34px rgba(255, 107, 53, 0.28);
      }}

      button:disabled {{
        cursor: wait;
        opacity: 0.72;
      }}

      .secondary-button {{
        margin-top: 10px;
        color: var(--ink);
        background: rgba(20, 33, 61, 0.08);
        box-shadow: none;
      }}

      #statusMessage {{
        min-height: 24px;
        margin-top: 12px;
        color: rgba(20, 33, 61, 0.75);
      }}

      .history-shell {{
        margin-top: 22px;
        padding-top: 20px;
        border-top: 1px solid rgba(20, 33, 61, 0.08);
      }}

      .history-list {{
        display: grid;
        gap: 10px;
        max-height: 320px;
        overflow-y: auto;
      }}

      .history-item {{
        width: 100%;
        padding: 14px;
        border-radius: 16px;
        border: 1px solid rgba(20, 33, 61, 0.1);
        background: rgba(255, 255, 255, 0.75);
        color: var(--ink);
        text-align: left;
        box-shadow: none;
      }}

      .history-item.selected {{
        border-color: rgba(255, 107, 53, 0.42);
        background: rgba(255, 107, 53, 0.12);
      }}

      .history-title {{
        display: block;
        font-weight: 800;
      }}

      .history-meta {{
        display: block;
        margin-top: 4px;
        color: rgba(20, 33, 61, 0.68);
        font-size: 0.9rem;
      }}

      .runs-panel {{
        padding: 22px;
      }}

      .runs-header {{
        display: flex;
        justify-content: space-between;
        align-items: end;
        gap: 12px;
        margin-bottom: 18px;
      }}

      .runs-grid {{
        display: grid;
        gap: 14px;
      }}

      .run-card {{
        border-radius: 20px;
        border: 1px solid rgba(20, 33, 61, 0.1);
        background: rgba(255, 255, 255, 0.78);
        padding: 18px;
        animation: reveal 280ms ease both;
      }}

      .run-card.selected {{
        border-color: rgba(255, 107, 53, 0.42);
        box-shadow: 0 18px 40px rgba(255, 107, 53, 0.12);
      }}

      @keyframes reveal {{
        from {{
          opacity: 0;
          transform: translateY(10px);
        }}
        to {{
          opacity: 1;
          transform: translateY(0);
        }}
      }}

      .run-top {{
        display: flex;
        justify-content: space-between;
        gap: 14px;
        align-items: start;
      }}

      .run-title {{
        margin: 0;
        font-size: 1.1rem;
      }}

      .run-meta {{
        margin-top: 6px;
        color: rgba(20, 33, 61, 0.62);
        font-size: 0.94rem;
      }}

      .badge {{
        padding: 8px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }}

      .badge.queued, .badge.running {{
        background: rgba(244, 162, 97, 0.18);
        color: #8f4d07;
      }}

      .badge.succeeded {{
        background: rgba(23, 114, 69, 0.14);
        color: var(--success);
      }}

      .badge.failed {{
        background: rgba(162, 44, 41, 0.12);
        color: var(--danger);
      }}

      .badge.cancelled {{
        background: rgba(20, 33, 61, 0.12);
        color: rgba(20, 33, 61, 0.78);
      }}

      .summary-grid {{
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 10px;
        margin-top: 14px;
      }}

      .progress-block {{
        margin-top: 14px;
      }}

      .progress-track {{
        width: 100%;
        height: 12px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(20, 33, 61, 0.08);
      }}

      .progress-fill {{
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(135deg, var(--accent), var(--accent-2));
        transition: width 180ms ease;
      }}

      .progress-meta {{
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-top: 8px;
        color: rgba(20, 33, 61, 0.72);
        font-size: 0.92rem;
      }}

      .summary-item {{
        padding: 12px;
        border-radius: 16px;
        background: rgba(20, 33, 61, 0.04);
      }}

      .summary-item strong {{
        display: block;
        font-size: 1.1rem;
      }}

      .actions {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 14px;
      }}

      .link-button {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 142px;
        padding: 12px 14px;
        border-radius: 14px;
        text-decoration: none;
        font-weight: 700;
        color: white;
        background: linear-gradient(135deg, var(--accent-2), #1f7a70);
      }}

      .link-button.secondary {{
        background: linear-gradient(135deg, #31415f, #1f2b44);
      }}

      details {{
        margin-top: 14px;
        border-top: 1px solid rgba(20, 33, 61, 0.1);
        padding-top: 12px;
      }}

      summary {{
        cursor: pointer;
        font-weight: 700;
      }}

      ul {{
        padding-left: 18px;
      }}

      .empty {{
        padding: 30px 18px;
        text-align: center;
        border-radius: 20px;
        border: 1px dashed rgba(20, 33, 61, 0.18);
        background: rgba(255, 255, 255, 0.56);
        color: rgba(20, 33, 61, 0.68);
      }}

      .preview-photo {{
        width: 64px;
        height: 64px;
        object-fit: cover;
        border-radius: 12px;
        border: 1px solid rgba(20, 33, 61, 0.1);
        margin-right: 10px;
        flex: 0 0 auto;
      }}

      .preview-row {{
        display: flex;
        align-items: center;
      }}

      @media (max-width: 920px) {{
        .layout {{
          grid-template-columns: 1fr;
        }}

        .form-panel {{
          position: static;
        }}
      }}

      @media (max-width: 640px) {{
        .shell {{
          width: min(100% - 18px, 100%);
          margin-top: 18px;
        }}

        .hero, .form-panel, .runs-panel {{
          border-radius: 20px;
        }}

        .summary-grid {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
      }}
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <div class="eyebrow">Control Room</div>
        <h1>Gear Miner Agent UI</h1>
        <p>Enter a brand and product category, run a live web search across the open web, crawl deeper through paginated pages, and download the results as CSV or Excel with product photos saved as JPG or PNG when available.</p>
      </section>

      <section class="layout">
        <aside class="panel form-panel">
          <div class="eyebrow">Launch</div>
          <h2>Start a Mining Run</h2>
          <p class="subcopy">The first two prompts are the key inputs: brand and product category. The agent runs a live search, follows relevant pagination and product links, and exports Brand, Product Name, and a saved JPG or PNG product photo file path.</p>
          <form id="runForm">
            <div class="field">
              <label for="brand">Step 1: Brand</label>
              <input id="brand" name="brand" type="text" placeholder="Nike, adidas, HOKA" required />
              <small>Plain text brand name.</small>
            </div>

            <div class="field">
              <label for="category">Step 2: Product category</label>
              <input id="category" name="category" type="text" placeholder="Running shoes" value="Running shoes" required />
              <small>Human-friendly category text is supported. The live search tries current web results first, then falls back to configured sources if needed.</small>
            </div>

            <div class="field">
              <label>Output file</label>
              <div class="format-grid">
                <label class="format-option">
                  <input type="radio" name="export_format" value="csv" checked />
                  <span>CSV</span>
                </label>
                <label class="format-option">
                  <input type="radio" name="export_format" value="excel" />
                  <span>Excel</span>
                </label>
              </div>
            </div>

            <div class="field">
              <label for="allowDomains">Allow domains</label>
              <input id="allowDomains" name="allow_domains" type="text" placeholder="nike.com, runningwarehouse.com" />
              <small>Optional comma-separated allow list. Leave blank to let each discovered source crawl within its own domain.</small>
            </div>

            <div class="field">
              <label for="blockDomains">Block domains</label>
              <input id="blockDomains" name="block_domains" type="text" placeholder="ebay.com, amazon.com" />
              <small>Optional comma-separated block list. Matching domains and subdomains are skipped during crawling.</small>
            </div>

            <button id="runButton" type="submit">Run Gear Miner</button>
            <button id="resetButton" class="secondary-button" type="button" disabled>Terminate Selected Search</button>
            <div id="statusMessage" aria-live="polite"></div>
          </form>

          <section class="history-shell">
            <div class="eyebrow">History</div>
            <h2>Search History</h2>
            <p class="subcopy">Select any prior search to terminate it if it is still running, or clear it after completion.</p>
            <div id="historyRoot" class="history-list"></div>
          </section>
        </aside>

        <section class="panel runs-panel">
          <div class="runs-header">
            <div>
              <div class="eyebrow">Manage</div>
              <h2>Recent Runs</h2>
            </div>
            <p class="subcopy">Completed live-search exports and saved product photos stay here so you can download them again later.</p>
          </div>
          <div id="runsRoot" class="runs-grid"></div>
        </section>
      </section>
    </main>

    <script>
      const initialRuns = {initial_runs_json};
      let currentRuns = initialRuns;
      let selectedRunId = initialRuns.length ? initialRuns[0].run_id : null;
      const runsRoot = document.getElementById("runsRoot");
      const historyRoot = document.getElementById("historyRoot");
      const runForm = document.getElementById("runForm");
      const runButton = document.getElementById("runButton");
      const resetButton = document.getElementById("resetButton");
      const statusMessage = document.getElementById("statusMessage");

      function escapeHtml(value) {{
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }}

      function formatTimestamp(value) {{
        if (!value) return "Pending";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
      }}

      function latestRun(runs) {{
        return runs.length ? runs[0] : null;
      }}

      function getRunById(runs, runId) {{
        return runs.find((run) => run.run_id === runId) || null;
      }}

      function syncSelectedRun(runs) {{
        if (!runs.length) {{
          selectedRunId = null;
          return null;
        }}

        const selected = getRunById(runs, selectedRunId);
        if (selected) {{
          return selected;
        }}

        const latest = latestRun(runs);
        selectedRunId = latest ? latest.run_id : null;
        return latest;
      }}

      function syncResetButton(runs) {{
        const run = syncSelectedRun(runs);
        if (!run) {{
          resetButton.disabled = true;
          resetButton.textContent = "Terminate Selected Search";
          return;
        }}

        if (run.status === "queued" || run.status === "running") {{
          resetButton.disabled = false;
          resetButton.textContent = "Terminate Selected Search";
          return;
        }}

        resetButton.disabled = false;
        resetButton.textContent = "Clear Selected Search";
      }}

      function formatPrice(product) {{
        if (product.price === null || product.price === undefined || product.price === "") {{
          return "Price unavailable";
        }}
        const currency = product.currency ? `${{product.currency}} ` : "";
        return `${{currency}}${{product.price}}`;
      }}

      function renderHistory(runs) {{
        const selected = syncSelectedRun(runs);
        if (!runs.length) {{
          historyRoot.innerHTML = '<div class="empty">No searches yet. Your run history will appear here.</div>';
          return;
        }}

        historyRoot.innerHTML = runs.map((run) => {{
          const selectedClass = selected && run.run_id === selected.run_id ? " selected" : "";
          return `
            <button type="button" class="history-item${{selectedClass}}" data-run-id="${{escapeHtml(run.run_id)}}">
              <span class="history-title">${{escapeHtml(run.brand)}} · ${{escapeHtml(run.category_input)}}</span>
              <span class="history-meta">${{escapeHtml(formatTimestamp(run.created_at))}} · ${{escapeHtml(run.status)}} · ${{escapeHtml(run.export_format.toUpperCase())}}</span>
            </button>
          `;
        }}).join("");
      }}

      function renderRuns(runs) {{
        currentRuns = runs;
        const selected = syncSelectedRun(runs);
        renderHistory(runs);
        if (!runs.length) {{
          syncResetButton(runs);
          runsRoot.innerHTML = '<div class="empty">No mining runs yet. Start with a brand and product category to create your first live-search export.</div>';
          return;
        }}

        syncResetButton(runs);
        runsRoot.innerHTML = runs.map((run) => {{
          const summary = run.summary || {{}};
          const preview = Array.isArray(run.product_preview) ? run.product_preview : [];
          const outcomes = Array.isArray(run.outcomes) ? run.outcomes : [];
          const warnings = Array.isArray(run.warnings) ? run.warnings : [];
          const actions = [];
          const progressTotal = Math.max(Number(run.progress_total || 100), 1);
          const progressCurrent = Math.min(Math.max(Number(run.progress_current || 0), 0), progressTotal);
          const progressPercent = Math.round((progressCurrent / progressTotal) * 100);
          const allowDomains = Array.isArray(run.allow_domains) ? run.allow_domains : [];
          const blockDomains = Array.isArray(run.block_domains) ? run.block_domains : [];
          const controls = [];
          const selectedClass = selected && run.run_id === selected.run_id ? " selected" : "";

          if (allowDomains.length) {{
            controls.push(`Allow ${{allowDomains.join(", ")}}`);
          }} else {{
            controls.push("Allow source domains");
          }}
          if (blockDomains.length) {{
            controls.push(`Block ${{blockDomains.join(", ")}}`);
          }}

          if (run.export_path) {{
            const outputLabel = run.export_format === "excel" ? "Download Excel" : "Download CSV";
            actions.push(`<a class="link-button" href="/download/${{run.run_id}}/output">${{outputLabel}}</a>`);
          }}
          if (run.snapshot_path) {{
            actions.push('<a class="link-button secondary" href="/download/' + run.run_id + '/snapshot">Download Snapshot</a>');
          }}

          const outcomeItems = outcomes.map((outcome) => {{
            const source = outcome.source || {{}};
            const error = outcome.error ? ` - ${{escapeHtml(outcome.error)}}` : "";
            return `<li><strong>${{escapeHtml(source.name || "Source")}}</strong>: ${{escapeHtml(outcome.status || "unknown")}}${{error}}</li>`;
          }}).join("");

          const previewItems = preview.map((product) => {{
            const url = product.product_url ? `<a href="${{escapeHtml(product.product_url)}}" target="_blank" rel="noreferrer">Open product</a>` : "";
            const photo = product.photo_name ? `<img class="preview-photo" src="/media/${{run.run_id}}/${{encodeURIComponent(product.photo_name)}}" alt="${{escapeHtml(product.name)}}" />` : "";
            const photoNote = product.photo_name ? ` • Photo: ${{escapeHtml(product.photo_name)}}` : " • Photo unavailable";
            return `<li><div class="preview-row">${{photo}}<div><strong>${{escapeHtml(product.brand)}}</strong> • ${{escapeHtml(product.name)}}${{photoNote}} ${{url}}</div></div></li>`;
          }}).join("");

          const warningItems = warnings.map((warning) => `<li>${{escapeHtml(warning)}}</li>`).join("");
          const errorBlock = run.error ? `<p style="color: var(--danger); margin: 12px 0 0;">${{escapeHtml(run.error)}}</p>` : "";

          return `
            <article class="run-card${{selectedClass}}">
              <div class="run-top">
                <div>
                  <h3 class="run-title">${{escapeHtml(run.brand)}} · ${{escapeHtml(run.category_input)}}</h3>
                  <div class="run-meta">Created ${{escapeHtml(formatTimestamp(run.created_at))}} · Live web search · Output ${{escapeHtml(run.export_format.toUpperCase())}}</div>
                  <div class="run-meta">${{escapeHtml(controls.join(" · "))}}</div>
                </div>
                <span class="badge ${{escapeHtml(run.status)}}">${{escapeHtml(run.status)}}</span>
              </div>
              <div class="progress-block">
                <div class="progress-track">
                  <div class="progress-fill" style="width: ${{progressPercent}}%;"></div>
                </div>
                <div class="progress-meta">
                  <span>${{escapeHtml(run.progress_label || "Queued")}}</span>
                  <span>${{progressPercent}}%</span>
                </div>
              </div>
              <div class="summary-grid">
                <div class="summary-item">
                  <strong>${{summary.products ?? 0}}</strong>
                  <span>Products</span>
                </div>
                <div class="summary-item">
                  <strong>${{summary.unique_models ?? 0}}</strong>
                  <span>Unique products</span>
                </div>
                <div class="summary-item">
                  <strong>${{summary.pages_crawled ?? 0}}</strong>
                  <span>Pages crawled</span>
                </div>
                <div class="summary-item">
                  <strong>${{summary.succeeded_sources ?? 0}}</strong>
                  <span>Successful sources</span>
                </div>
                <div class="summary-item">
                  <strong>${{summary.failed_sources ?? 0}}</strong>
                  <span>Failed sources</span>
                </div>
                <div class="summary-item">
                  <strong>${{summary.photos_saved ?? 0}}</strong>
                  <span>Photos saved</span>
                </div>
              </div>
              ${{errorBlock}}
              <div class="actions">${{actions.join("")}}</div>
              <details>
                <summary>Warnings</summary>
                <ul>${{warningItems || "<li>No warnings recorded.</li>"}}</ul>
              </details>
              <details>
                <summary>Source outcomes</summary>
                <ul>${{outcomeItems || "<li>No source results yet.</li>"}}</ul>
              </details>
              <details>
                <summary>Product preview</summary>
                <ul>${{previewItems || "<li>No products captured yet.</li>"}}</ul>
              </details>
            </article>
          `;
        }}).join("");
      }}

      async function refreshRuns() {{
        const response = await fetch("/api/runs");
        const payload = await response.json();
        renderRuns(payload.runs || []);
      }}

      runForm.addEventListener("submit", async (event) => {{
        event.preventDefault();
        runButton.disabled = true;
        statusMessage.textContent = "Launching the live web mining run...";

        const formData = new FormData(runForm);
        const body = new URLSearchParams();
        for (const [key, value] of formData.entries()) {{
          body.append(key, value);
        }}

        try {{
          const response = await fetch("/api/runs", {{
            method: "POST",
            headers: {{ "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" }},
            body,
          }});
          const payload = await response.json();
          if (!response.ok) {{
            throw new Error(payload.error || "Unable to start the mining run.");
          }}
          selectedRunId = payload.run && payload.run.run_id ? payload.run.run_id : selectedRunId;
          statusMessage.textContent = "Run started. The progress bar will update as live search, crawling, photos, and export steps complete.";
          await refreshRuns();
        }} catch (error) {{
          statusMessage.textContent = error.message;
        }} finally {{
          runButton.disabled = false;
        }}
      }});

      resetButton.addEventListener("click", async () => {{
        const run = syncSelectedRun(currentRuns);
        if (!run) {{
          statusMessage.textContent = "Select a search from history first.";
          renderRuns(currentRuns);
          return;
        }}

        resetButton.disabled = true;
        statusMessage.textContent = run.status === "queued" || run.status === "running"
          ? "Requesting cancellation for the selected search..."
          : "Clearing the selected search...";

        try {{
          const response = await fetch(`/api/runs/${{run.run_id}}/reset`, {{
            method: "POST",
          }});
          const payload = await response.json();
          if (!response.ok) {{
            throw new Error(payload.error || "Unable to update the selected search.");
          }}

          if (payload.action === "cancel_requested") {{
            statusMessage.textContent = "Cancellation requested for the selected search.";
          }} else {{
            statusMessage.textContent = "Selected search cleared. The agent is ready for a new search.";
            runForm.reset();
            document.getElementById("category").value = "Running shoes";
            document.getElementById("brand").focus();
          }}
          await refreshRuns();
        }} catch (error) {{
          statusMessage.textContent = error.message;
          await refreshRuns();
        }}
      }});

      historyRoot.addEventListener("click", (event) => {{
        const button = event.target.closest("[data-run-id]");
        if (!button) {{
          return;
        }}
        selectedRunId = button.getAttribute("data-run-id");
        renderRuns(currentRuns);
      }});

      renderRuns(initialRuns);
      window.setInterval(() => {{
        refreshRuns().catch(() => undefined);
      }}, 2500);
    </script>
  </body>
</html>"""


def serve_ui(host: str = "127.0.0.1", port: int = 8765, data_dir: Optional[Path] = None) -> int:
    server = create_server(host=host, port=port, data_dir=data_dir)
    print(f"Gear Miner UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Gear Miner UI.")
    finally:
        server.server_close()
    return 0
