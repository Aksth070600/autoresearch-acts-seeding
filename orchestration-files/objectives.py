"""Deterministic record loading and primary-objective comparison."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol import PROTOCOL_METADATA, is_compatible_summary

PRIMARY_TIME_METRIC = "seeding_time_per_event_ms"
PRIMARY_EFFICIENCY_METRIC = "ambiguity_particle_efficiency"
PRIMARY_METRICS = (PRIMARY_TIME_METRIC, PRIMARY_EFFICIENCY_METRIC)
FULL_CHAIN_TIME_METRIC = "total_time_per_event_ms"


class SelectionError(RuntimeError):
    """Raised when controlled records cannot support deterministic selection."""


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def stage_prefix(stage: dict[str, Any]) -> str | None:
    name = str(stage.get("name", ""))
    if "timed" in name or stage.get("metrics_mode") == "time":
        return "timed"
    if stage.get("metrics_mode") == "none" and stage.get("events", 0) > 1:
        return "clean"
    return None


def add_run_metrics(
    metrics: dict[str, float], prefix: str, run_metrics: dict[str, Any]
) -> None:
    """Flatten the two objectives and the full-chain timing diagnostic."""

    total_time = run_metrics.get("timing_total", {}).get("time_per_event_ms")
    if finite(total_time):
        metrics[f"{prefix}_{FULL_CHAIN_TIME_METRIC}"] = float(total_time)

    seeding_time = (
        run_metrics.get("timing", {}).get("seeding", {}).get("time_per_event_ms")
    )
    if finite(seeding_time):
        metrics[f"{prefix}_{PRIMARY_TIME_METRIC}"] = float(seeding_time)

    efficiency = (
        run_metrics.get("performance", {})
        .get("ambiguity_resolution", {})
        .get("efficiency_particles")
    )
    if finite(efficiency):
        metrics[f"{prefix}_{PRIMARY_EFFICIENCY_METRIC}"] = float(efficiency)


def flatten_summary(
    summary: dict[str, Any], path: Path, records_root: Path
) -> dict[str, Any] | None:
    if summary.get("status") != "passed" or not is_compatible_summary(summary):
        return None
    stages = summary.get("stages")
    if (
        not isinstance(stages, list)
        or not stages
        or any(
            not isinstance(stage, dict) or stage.get("status") != "passed"
            for stage in stages
        )
    ):
        return None

    metrics: dict[str, float] = {}
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("comparison") != "clean":
            continue
        if stage_prefix(stage) == "clean" and isinstance(stage.get("run_metrics"), dict):
            add_run_metrics(metrics, "clean", stage["run_metrics"])

    comparison = summary.get("timed_comparison", {})
    if not isinstance(comparison, dict):
        comparison = {}
    repetitions = comparison.get("repetitions")
    median_metrics = comparison.get("median_run_metrics")
    if (
        comparison.get("complete") is True
        and comparison.get("aggregation") == PROTOCOL_METADATA["timed_aggregation"]
        and comparison.get("repetition_count") == PROTOCOL_METADATA["timed_repetitions"]
        and isinstance(repetitions, list)
        and len(repetitions) == PROTOCOL_METADATA["timed_repetitions"]
        and all(
            isinstance(repetition, dict)
            and repetition.get("status") == "passed"
            and isinstance(repetition.get("run_metrics"), dict)
            and bool(repetition.get("run_metrics"))
            for repetition in repetitions
        )
        and isinstance(median_metrics, dict)
    ):
        add_run_metrics(metrics, "timed", median_metrics)

    required = {f"timed_{name}" for name in PRIMARY_METRICS}
    if not required.issubset(metrics):
        return None
    candidate = str(summary.get("candidate_name", path.parent.name))
    return {
        "candidate": candidate,
        "category": str(summary.get("category", path.parent.parent.name)),
        "commit": str(summary.get("implementation_commit", "")),
        "record": path.relative_to(records_root).as_posix(),
        "status": str(summary.get("status", "")),
        "is_baseline": bool(summary.get("baseline", candidate == "Genesis")),
        "started_at": str(summary.get("started_at", "")),
        "finished_at": str(summary.get("finished_at", "")),
        "metrics": metrics,
    }


def load_records(records_root: Path, dataset: str) -> list[dict[str, Any]]:
    """Load complete protocol-compatible summaries in deterministic path order."""

    rows: list[dict[str, Any]] = []
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not is_compatible_summary(summary):
            continue
        category = str(summary.get("category", path.parent.parent.name)).lower()
        if dataset != "all" and category != dataset:
            continue
        row = flatten_summary(summary, path, records_root)
        if row is not None:
            rows.append(row)
    return rows


def _record_timestamp(row: dict[str, Any]) -> datetime:
    for field in ("started_at", "finished_at"):
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    return timestamp.replace(tzinfo=timezone.utc)
                return timestamp.astimezone(timezone.utc)
            except ValueError:
                pass

    match = re.search(
        r"/(\d{8}T\d{6}(?:\d{6})?Z)(?:-\d+)?-Genesis/summary\.json$",
        "/" + str(row.get("record", "")),
    )
    if match:
        for date_format in ("%Y%m%dT%H%M%S%fZ", "%Y%m%dT%H%M%SZ"):
            try:
                return datetime.strptime(match.group(1), date_format).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
    return datetime.min.replace(tzinfo=timezone.utc)


def choose_baseline(
    rows: list[dict[str, Any]], candidate_name: str
) -> dict[str, Any]:
    """Choose the newest complete Development Genesis record."""

    matches = [
        row
        for row in rows
        if row["candidate"] == candidate_name
        and row["category"].lower() == "development"
        and row.get("is_baseline", True)
        and row.get("status", "passed") == "passed"
    ]
    if not matches:
        raise SelectionError(
            "protocol-compatible Development Genesis baseline required; "
            "run `make evaluate CANDIDATE=Genesis` first"
        )
    return max(
        matches,
        key=lambda row: (_record_timestamp(row), str(row.get("record", ""))),
    )


def improved_over_baseline(
    row: dict[str, Any], baseline: dict[str, Any], stage: str = "timed"
) -> bool:
    metrics = row["metrics"]
    base = baseline["metrics"]
    required = tuple(f"{stage}_{name}" for name in PRIMARY_METRICS)
    if any(name not in metrics or name not in base for name in required):
        return False
    return (
        metrics[f"{stage}_{PRIMARY_TIME_METRIC}"]
        < base[f"{stage}_{PRIMARY_TIME_METRIC}"]
        or metrics[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
        > base[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
    )


def dominates(
    left: dict[str, Any], right: dict[str, Any], stage: str = "timed"
) -> bool:
    """Return whether left is at least as good on both primary objectives."""

    left_time = left["metrics"][f"{stage}_{PRIMARY_TIME_METRIC}"]
    right_time = right["metrics"][f"{stage}_{PRIMARY_TIME_METRIC}"]
    left_efficiency = left["metrics"][f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
    right_efficiency = right["metrics"][f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
    return (
        left_time <= right_time
        and left_efficiency >= right_efficiency
        and (left_time < right_time or left_efficiency > right_efficiency)
    )


def time_first_key(row: dict[str, Any], stage: str = "timed") -> tuple[float, float, str]:
    """Return the deterministic time-first tie-break used after Pareto filtering."""

    return (
        row["metrics"][f"{stage}_{PRIMARY_TIME_METRIC}"],
        -row["metrics"][f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"],
        row["record"],
    )


def pareto_front(
    rows: list[dict[str, Any]], stage: str = "timed"
) -> list[dict[str, Any]]:
    """Return primary-objective candidates in deterministic time-first order."""

    front = [
        row
        for row in rows
        if not any(
            other is not row and dominates(other, row, stage) for other in rows
        )
    ]
    return sorted(front, key=lambda row: time_first_key(row, stage))
