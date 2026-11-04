from __future__ import annotations

import urllib.request
from datetime import datetime, timezone

from .state import IngestState

# A longer gap between two finished images counts as a pause, not as time spent.
PAUSE_SECONDS = 900

METADATA_SERVICE = "http://169.254.169.254/latest"
METADATA_TIMEOUT_SECONDS = 1
METADATA_TOKEN_SECONDS = "60"

MAX_FAILED_FILES = 100


def cloud_machine_type() -> str | None:
    try:
        token_request = urllib.request.Request(
            f"{METADATA_SERVICE}/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": METADATA_TOKEN_SECONDS},
        )
        with urllib.request.urlopen(
            token_request, timeout=METADATA_TIMEOUT_SECONDS
        ) as response:
            token = response.read().decode()
        type_request = urllib.request.Request(
            f"{METADATA_SERVICE}/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(
            type_request, timeout=METADATA_TIMEOUT_SECONDS
        ) as response:
            return response.read().decode().strip() or None
    except Exception:
        return None


def active_seconds(finish_times: list[int], first_item_seconds: float) -> float:
    if not finish_times:
        return 0.0
    gaps = (later - earlier for earlier, later in zip(finish_times, finish_times[1:]))
    return first_item_seconds + sum(gap for gap in gaps if gap <= PAUSE_SECONDS)


def iso(epoch_seconds: float | None) -> str | None:
    if epoch_seconds is None:
        return None
    moment = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_report(state: IngestState) -> dict:
    counts = state.counts()
    finish_times = state.finish_times()
    first_item_seconds = state.first_item_seconds()
    seconds = active_seconds(finish_times, first_item_seconds)
    indexed = counts.get("done", 0)
    bytes_read = state.bytes_read()
    is_finished = bool(finish_times) and counts.get("pending", 0) == 0
    estimate = state.fact("estimated_seconds")
    return {
        "started_at": (
            iso(finish_times[0] - first_item_seconds) if finish_times else None
        ),
        "finished_at": iso(finish_times[-1]) if is_finished else None,
        "active_seconds": round(seconds, 1),
        "estimated_seconds": float(estimate) if estimate else None,
        "images_per_second": round(indexed / seconds, 2) if seconds else None,
        "source_bytes_read": bytes_read,
        "megabytes_per_second": (
            round(bytes_read / 1024**2 / seconds, 1) if seconds else None
        ),
        "model_name": state.fact("model_name"),
        "device": state.fact("device"),
        "machine_type": state.fact("machine_type"),
        "failed_files": [
            {"file": key, "reason": reason}
            for key, reason in state.failed_files(MAX_FAILED_FILES)
        ],
    }


def human_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, minutes = seconds // 3600, seconds % 3600 // 60
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {seconds % 60} s"
    return f"{seconds} s"


def human_bytes(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024


def render_report(summary: dict) -> str:
    run = summary["run"]
    lines = [
        f"Indexing: {'finished' if run['finished_at'] else 'in progress'}",
        f"  Indexed {summary['indexed']:,}, skipped {summary['skipped']:,}, "
        f"failed {summary['failed']:,}, waiting {summary['pending']:,}",
    ]
    if run["started_at"]:
        lines.append(f"  Started   {run['started_at']}")
    if run["finished_at"]:
        lines.append(f"  Finished  {run['finished_at']}")
    if run["active_seconds"]:
        lines.append(
            f"  Time spent indexing: {human_duration(run['active_seconds'])} "
            f"({run['images_per_second']} images/s, {run['megabytes_per_second']} MB/s)"
        )
    if run["estimated_seconds"] and run["finished_at"]:
        lines.append(
            f"  The estimate beforehand was {human_duration(run['estimated_seconds'])}"
        )
    lines.append(f"  Read from the source: {human_bytes(run['source_bytes_read'])}")
    disk = summary["disk_bytes_measured"]
    lines.append(f"  Disk used by this collection: {human_bytes(disk['total'])}")
    described = [
        f"model {run['model_name']}" if run["model_name"] else "",
        f"on {run['device']}" if run["device"] else "",
        f"machine {run['machine_type']}" if run["machine_type"] else "",
    ]
    lines.append("  " + ", ".join(part for part in described if part))
    for problem in summary["problems"]:
        lines.append(f"  {problem['status']} {problem['count']:,}: {problem['reason']}")
    for failed in run["failed_files"][:10]:
        lines.append(f"    {failed['file']}")
    if len(run["failed_files"]) > 10:
        lines.append(
            f"    and {len(run['failed_files']) - 10} more in the JSON summary"
        )
    return "\n".join(lines)
