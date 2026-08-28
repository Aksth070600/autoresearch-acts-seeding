"""Deterministic record loading and primary-objective comparison."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from proposal import ProposalError, proposal_from_summary
from protocol import (
    PROTOCOL_ID,
    PROTOCOL_METADATA,
    is_complete_rss_evidence,
    is_complete_stage_matrix,
    seeding_objective_protocol,
)

PRIMARY_TIME_METRIC = "seeding_time_per_event_ms"
PRIMARY_EFFICIENCY_METRIC = "seeding_particle_efficiency"
PRIMARY_METRICS = (PRIMARY_TIME_METRIC, PRIMARY_EFFICIENCY_METRIC)
class SelectionError(RuntimeError):
    """Raised when controlled records cannot support deterministic selection."""


def finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def add_run_metrics(
    metrics: dict[str, float], prefix: str, run_metrics: dict[str, Any]
) -> None:
    """Flatten only the two shared v2/v3 primary objectives."""

    seeding_time = (
        run_metrics.get("timing", {}).get("seeding", {}).get("time_per_event_ms")
    )
    if finite(seeding_time):
        metrics[f"{prefix}_{PRIMARY_TIME_METRIC}"] = float(seeding_time)

    efficiency = (
        run_metrics.get("performance", {})
        .get("seeding", {})
        .get("efficiency_particles")
    )
    if finite(efficiency):
        metrics[f"{prefix}_{PRIMARY_EFFICIENCY_METRIC}"] = float(efficiency)


def flatten_summary(
    summary: dict[str, Any], path: Path, records_root: Path
) -> dict[str, Any] | None:
    protocol = seeding_objective_protocol(summary)
    if summary.get("status") != "passed" or protocol is None:
        return None
    stages = summary.get("stages")
    if protocol["id"] == PROTOCOL_ID:
        if not is_complete_stage_matrix(stages) or not is_complete_rss_evidence(
            summary.get("rss_evidence")
        ):
            return None
    elif (
        not isinstance(stages, list)
        or not stages
        or any(
            not isinstance(stage, dict) or stage.get("status") != "passed"
            for stage in stages
        )
    ):
        return None

    metrics: dict[str, float] = {}
    comparison = summary.get("timed_comparison", {})
    if not isinstance(comparison, dict):
        comparison = {}
    repetitions = comparison.get("repetitions")
    median_metrics = comparison.get("median_run_metrics")
    expected_repetitions = int(protocol["timed_repetitions"])
    category = str(summary.get("category", path.parent.parent.name)).lower()
    if protocol["id"] != PROTOCOL_ID and category not in {"development", "evaluation"}:
        return None
    expected_events = (
        int(PROTOCOL_METADATA["timing_events"])
        if protocol["id"] == PROTOCOL_ID
        else int(protocol[f"{category}_events"])
    )
    repetitions_complete = (
        isinstance(repetitions, list)
        and len(repetitions) == expected_repetitions
        and all(
            isinstance(repetition, dict)
            and repetition.get("status") == "passed"
            and repetition.get("events") == expected_events
            and isinstance(repetition.get("run_metrics"), dict)
            and bool(repetition.get("run_metrics"))
            for repetition in repetitions
        )
    )
    if protocol["id"] == PROTOCOL_ID and repetitions_complete:
        repetitions_complete = all(
            repetition.get("stage") == PROTOCOL_METADATA["execution_stage"]
            and repetition.get("metrics_mode")
            == PROTOCOL_METADATA["timing_instrumentation"]
            and not repetition.get("resource_metrics")
            for repetition in repetitions
        )
    if (
        comparison.get("complete") is True
        and comparison.get("aggregation") == protocol["timed_aggregation"]
        and comparison.get("events") == expected_events
        and comparison.get("repetition_count") == expected_repetitions
        and repetitions_complete
        and isinstance(median_metrics, dict)
    ):
        add_run_metrics(metrics, "timed", median_metrics)

    required = {f"timed_{name}" for name in PRIMARY_METRICS}
    if not required.issubset(metrics):
        return None
    candidate = str(summary.get("candidate_name", path.parent.name))
    try:
        proposal = proposal_from_summary(summary)
    except ProposalError:
        return None
    if candidate != "Genesis" and proposal is None:
        return None
    return {
        "candidate": candidate,
        "category": str(summary.get("category", path.parent.parent.name)),
        "protocol_id": str(protocol["id"]),
        "source_protocol_id": str(protocol["id"]),
        "commit": str(summary.get("implementation_commit", "")),
        "record": path.relative_to(records_root).as_posix(),
        "status": str(summary.get("status", "")),
        "is_baseline": bool(summary.get("baseline", candidate == "Genesis")),
        "started_at": str(summary.get("started_at", "")),
        "finished_at": str(summary.get("finished_at", "")),
        "metrics": metrics,
        "proposal": proposal,
        "candidate_identity": summary.get("candidate_identity"),
    }


def load_records(records_root: Path, dataset: str) -> list[dict[str, Any]]:
    """Load complete seeding-objective-family summaries in path order."""

    rows: list[dict[str, Any]] = []
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if seeding_objective_protocol(summary) is None:
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
            "seeding-objective-compatible Development Genesis baseline required; "
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
