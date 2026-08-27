#!/usr/bin/env python3
"""Generate a validated live-campaign snapshot from Development summaries."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import quote

from protocol import (
    CAMPAIGN_ATTEMPT_POLICY,
    PROTOCOL_ID,
    PROTOCOL_METADATA,
    is_compatible_summary,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = PROJECT_ROOT / "records"
DEFAULT_INPUT = PROJECT_ROOT / "campaign-status-input.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "campaign-status.json"
REPOSITORY_URL = "https://github.com/Aksth070600/autoresearch-acts-seeding"
STATUS_SCHEMA_VERSION = "1.0.0"
STATUS_SCHEMA_URL = (
    "https://raw.githubusercontent.com/Aksth070600/autoresearch-acts-seeding/"
    "main/orchestration-files/campaign-status.schema.json"
)
COMPLETED_ATTEMPT_TARGET = CAMPAIGN_ATTEMPT_POLICY["completed_attempt_target"]
STRUCTURAL_ATTEMPT_TARGET = CAMPAIGN_ATTEMPT_POLICY["structural_attempt_target"]
MICRO_OPTIMIZATION_CAP = CAMPAIGN_ATTEMPT_POLICY["micro_optimization_cap"]
ETA_MINIMUM_SAMPLES = 3
STALE_AFTER_SECONDS = 15 * 60
FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
CANDIDATE_NAME = re.compile(r"[A-Za-z0-9._-]+")
PULL_REQUEST_URL = re.compile(
    re.escape(REPOSITORY_URL) + r"/pull/[1-9][0-9]*"
)
CLASSIFICATIONS = {"baseline", "structural", "micro"}
CURRENT_STATES = {"queued", "running", "recording", "blocked"}


class StatusError(ValueError):
    """Raised when campaign state or derived evidence is invalid."""


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def parse_instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise StatusError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StatusError(f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise StatusError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_ref(value: Any) -> str:
    """Validate a Git ref using the safe subset shared with the dashboard."""

    if not isinstance(value, str):
        raise StatusError("campaign.branch must be a string")
    ref = value.strip()
    forbidden = ("..", "@{", "\\", "~", "^", ":", "?", "*", "[")
    if (
        not ref
        or len(ref) > 200
        or ref.startswith(("/", "-", "."))
        or ref.endswith(("/", "."))
        or "//" in ref
        or any(token in ref for token in forbidden)
        or any(ord(character) < 33 or ord(character) == 127 for character in ref)
    ):
        raise StatusError("campaign.branch is not a safe Git ref")
    segments = ref.split("/")
    if any(
        not segment
        or segment in {".", ".."}
        or segment.startswith(".")
        or segment.endswith(".lock")
        for segment in segments
    ):
        raise StatusError("campaign.branch is not a safe Git ref")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", ref):
        raise StatusError("campaign.branch is not a safe Git ref")
    return ref


def validate_label(value: Any, field: str, *, maximum: int = 120) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise StatusError(f"{field} must be a non-empty string of at most {maximum} characters")
    result = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in result):
        raise StatusError(f"{field} contains a control character")
    return result


def require_keys(value: dict[str, Any], field: str, allowed: set[str], required: set[str]) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise StatusError(f"{field} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise StatusError(f"{field} has unsupported fields: {', '.join(sorted(unknown))}")


def validate_attempt_metadata(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise StatusError(f"{field} must be an object")
    allowed = {"candidate", "mechanism_family", "classification"}
    require_keys(value, field, allowed, allowed)
    candidate = validate_label(value["candidate"], f"{field}.candidate", maximum=80)
    if not CANDIDATE_NAME.fullmatch(candidate):
        raise StatusError(f"{field}.candidate has unsupported characters")
    mechanism = validate_label(value["mechanism_family"], f"{field}.mechanism_family")
    classification = value["classification"]
    if classification not in {"structural", "micro"}:
        raise StatusError(f"{field}.classification must be structural or micro")
    return {
        "candidate": candidate,
        "mechanism_family": mechanism,
        "classification": classification,
    }


def validate_live_state(value: Any) -> dict[str, Any]:
    """Validate and normalize the small hand-maintained campaign state input."""

    if not isinstance(value, dict):
        raise StatusError("campaign status input must be an object")
    allowed = {
        "schema_version",
        "campaign",
        "current_attempt",
        "attempt_metadata",
        "blockers",
        "pull_request_url",
    }
    require_keys(value, "input", allowed, allowed)
    if value["schema_version"] != STATUS_SCHEMA_VERSION:
        raise StatusError(f"input.schema_version must be {STATUS_SCHEMA_VERSION}")

    campaign = value["campaign"]
    if not isinstance(campaign, dict):
        raise StatusError("input.campaign must be an object")
    campaign_fields = {"name", "branch", "phase", "started_at"}
    require_keys(campaign, "input.campaign", campaign_fields, campaign_fields)
    normalized_campaign = {
        "name": validate_label(campaign["name"], "input.campaign.name"),
        "branch": validate_ref(campaign["branch"]),
        "phase": validate_label(campaign["phase"], "input.campaign.phase", maximum=60),
        "started_at": isoformat(parse_instant(campaign["started_at"], "input.campaign.started_at")),
    }

    metadata_input = value["attempt_metadata"]
    if not isinstance(metadata_input, list):
        raise StatusError("input.attempt_metadata must be an array")
    metadata = [
        validate_attempt_metadata(item, f"input.attempt_metadata[{index}]")
        for index, item in enumerate(metadata_input)
    ]
    candidates = [item["candidate"] for item in metadata]
    if len(candidates) != len(set(candidates)):
        raise StatusError("input.attempt_metadata candidate names must be unique")
    if "Genesis" in candidates:
        raise StatusError("Genesis metadata is derived and must not be listed")

    current_input = value["current_attempt"]
    current: dict[str, Any] | None = None
    if current_input is not None:
        if not isinstance(current_input, dict):
            raise StatusError("input.current_attempt must be an object or null")
        fields = {
            "candidate",
            "mechanism_family",
            "classification",
            "controlled_stage",
            "state",
            "started_at",
        }
        require_keys(current_input, "input.current_attempt", fields, fields)
        candidate = validate_label(
            current_input["candidate"], "input.current_attempt.candidate", maximum=80
        )
        if not CANDIDATE_NAME.fullmatch(candidate):
            raise StatusError("input.current_attempt.candidate has unsupported characters")
        classification = current_input["classification"]
        if classification not in CLASSIFICATIONS:
            raise StatusError("input.current_attempt.classification is invalid")
        if (candidate == "Genesis") != (classification == "baseline"):
            raise StatusError("only Genesis may use the baseline classification")
        if current_input["state"] not in CURRENT_STATES:
            raise StatusError("input.current_attempt.state is invalid")
        started_at = current_input["started_at"]
        if started_at is not None:
            started_at = isoformat(
                parse_instant(started_at, "input.current_attempt.started_at")
            )
            if parse_instant(started_at, "input.current_attempt.started_at") < parse_instant(
                normalized_campaign["started_at"], "input.campaign.started_at"
            ):
                raise StatusError("current attempt cannot start before the campaign")
        current = {
            "candidate": candidate,
            "mechanism_family": validate_label(
                current_input["mechanism_family"],
                "input.current_attempt.mechanism_family",
            ),
            "classification": classification,
            "controlled_stage": validate_label(
                current_input["controlled_stage"],
                "input.current_attempt.controlled_stage",
                maximum=80,
            ),
            "state": current_input["state"],
            "started_at": started_at,
        }
        if candidate != "Genesis":
            matching = [item for item in metadata if item["candidate"] == candidate]
            if not matching:
                raise StatusError("current non-Genesis candidate must be in attempt_metadata")
            if any(
                item["mechanism_family"] != current["mechanism_family"]
                or item["classification"] != current["classification"]
                for item in matching
            ):
                raise StatusError("current attempt does not match its attempt_metadata")

    blockers_input = value["blockers"]
    if not isinstance(blockers_input, list) or len(blockers_input) > 20:
        raise StatusError("input.blockers must be an array with at most 20 items")
    blockers = [
        validate_label(item, f"input.blockers[{index}]", maximum=500)
        for index, item in enumerate(blockers_input)
    ]

    pull_request_url = value["pull_request_url"]
    if pull_request_url is not None and (
        not isinstance(pull_request_url, str)
        or not PULL_REQUEST_URL.fullmatch(pull_request_url)
    ):
        raise StatusError("input.pull_request_url must be this repository's pull request URL or null")

    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "campaign": normalized_campaign,
        "current_attempt": current,
        "attempt_metadata": metadata,
        "blockers": blockers,
        "pull_request_url": pull_request_url,
    }


def objective_metrics(summary: dict[str, Any]) -> tuple[float, float]:
    comparison = summary.get("timed_comparison")
    if not isinstance(comparison, dict):
        raise StatusError("passed summary has no timed_comparison")
    repetitions = comparison.get("repetitions")
    if not (
        comparison.get("complete") is True
        and comparison.get("aggregation") == PROTOCOL_METADATA["timed_aggregation"]
        and comparison.get("repetition_count") == PROTOCOL_METADATA["timed_repetitions"]
        and isinstance(repetitions, list)
        and len(repetitions) == PROTOCOL_METADATA["timed_repetitions"]
    ):
        raise StatusError("passed summary has an incomplete timed comparison")
    median_metrics = comparison.get("median_run_metrics")
    try:
        seeding = median_metrics["timing"]["seeding"]["time_per_event_ms"]
        efficiency = median_metrics["performance"]["ambiguity_resolution"][
            "efficiency_particles"
        ]
    except (KeyError, TypeError) as error:
        raise StatusError("passed summary is missing a primary objective") from error
    if not finite_number(seeding) or seeding < 0:
        raise StatusError("timed seeding time/event must be a finite non-negative number")
    if not finite_number(efficiency) or not 0 <= efficiency <= 1:
        raise StatusError("particle ambiguity efficiency must be between zero and one")
    return float(seeding), float(efficiency)


def summary_passed(summary: dict[str, Any]) -> bool:
    stages = summary.get("stages")
    return (
        summary.get("status") == "passed"
        and str(summary.get("category", "")).lower() == "development"
        and isinstance(stages, list)
        and bool(stages)
        and all(isinstance(stage, dict) and stage.get("status") == "passed" for stage in stages)
    )


def repository_file_url(branch: str, record: str) -> str:
    return f"{REPOSITORY_URL}/blob/{quote(branch, safe='/')}/{quote(record, safe='/')}"


def commit_url(commit: Any) -> str | None:
    if isinstance(commit, str) and FULL_COMMIT_SHA.fullmatch(commit.lower()):
        return f"{REPOSITORY_URL}/commit/{commit.lower()}"
    return None


def load_attempts(records_root: Path, live_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Load protocol-compatible Development attempts belonging to this campaign."""

    campaign_start = parse_instant(live_state["campaign"]["started_at"], "campaign.started_at")
    metadata = {
        item["candidate"]: item for item in live_state["attempt_metadata"]
    }
    current = live_state["current_attempt"]
    if current is not None and current["candidate"] != "Genesis":
        metadata[current["candidate"]] = {
            "candidate": current["candidate"],
            "mechanism_family": current["mechanism_family"],
            "classification": current["classification"],
        }

    attempts: list[dict[str, Any]] = []
    if not records_root.is_dir():
        raise StatusError(f"records directory not found: {records_root}")
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StatusError(f"cannot read summary {path}: {error}") from error
        if not isinstance(summary, dict) or not is_compatible_summary(summary):
            continue
        if str(summary.get("mode", "development")).lower() != "development":
            continue
        started_value = summary.get("started_at")
        if not isinstance(started_value, str):
            continue
        started = parse_instant(started_value, f"{path}: started_at")
        if started < campaign_start:
            continue
        candidate = summary.get("candidate_name")
        if not isinstance(candidate, str) or not CANDIDATE_NAME.fullmatch(candidate):
            raise StatusError(f"{path}: invalid candidate_name")
        if candidate == "Genesis":
            mechanism_family = "fresh Genesis baseline"
            classification = "baseline"
        else:
            item = metadata.get(candidate)
            if item is None:
                raise StatusError(
                    f"{path}: add non-scientific metadata for candidate {candidate!r}"
                )
            mechanism_family = item["mechanism_family"]
            classification = item["classification"]

        finished_value = summary.get("finished_at")
        finished = (
            parse_instant(finished_value, f"{path}: finished_at")
            if isinstance(finished_value, str)
            else None
        )
        if finished is not None and finished < started:
            raise StatusError(f"{path}: finished_at precedes started_at")
        duration_seconds = (
            round((finished - started).total_seconds(), 3) if finished is not None else None
        )
        passed = summary_passed(summary)
        if summary.get("status") == "passed" and not passed:
            raise StatusError(f"{path}: passed summary does not contain all Development stages")
        seeding: float | None = None
        efficiency: float | None = None
        if passed:
            seeding, efficiency = objective_metrics(summary)
        relative = path.relative_to(records_root).as_posix()
        error = summary.get("error")
        failure_message = (
            validate_label(error, f"{path}: error", maximum=500)
            if isinstance(error, str) and error.strip()
            else "Controlled Development attempt did not pass."
        )
        attempts.append(
            {
                "candidate": candidate,
                "mechanism_family": mechanism_family,
                "classification": classification,
                "state": "completed" if passed else "failed",
                "outcome": "Passed all controlled Development stages." if passed else failure_message,
                "started_at": isoformat(started),
                "finished_at": isoformat(finished) if finished is not None else None,
                "duration_seconds": duration_seconds,
                "timed_seeding_time_per_event_ms": seeding,
                "timed_ambiguity_particle_efficiency": efficiency,
                "implementation_commit": (
                    str(summary.get("implementation_commit"))
                    if commit_url(summary.get("implementation_commit"))
                    else None
                ),
                "links": {
                    "commit": commit_url(summary.get("implementation_commit")),
                    "record": repository_file_url(
                        live_state["campaign"]["branch"],
                        f"records/{relative}",
                    ),
                },
                "record": f"records/{relative}",
            }
        )
    attempts.sort(key=lambda item: (item["started_at"], item["record"]))
    return attempts


def result_point(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": attempt["candidate"],
        "timed_seeding_time_per_event_ms": attempt["timed_seeding_time_per_event_ms"],
        "timed_ambiguity_particle_efficiency": attempt[
            "timed_ambiguity_particle_efficiency"
        ],
        "started_at": attempt["started_at"],
        "links": dict(attempt["links"]),
    }


def pareto_front(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = [attempt for attempt in attempts if attempt["state"] == "completed"]
    front = []
    for candidate in completed:
        candidate_time = candidate["timed_seeding_time_per_event_ms"]
        candidate_efficiency = candidate["timed_ambiguity_particle_efficiency"]
        dominated = any(
            other is not candidate
            and other["timed_seeding_time_per_event_ms"] <= candidate_time
            and other["timed_ambiguity_particle_efficiency"] >= candidate_efficiency
            and (
                other["timed_seeding_time_per_event_ms"] < candidate_time
                or other["timed_ambiguity_particle_efficiency"] > candidate_efficiency
            )
            for other in completed
        )
        if not dominated:
            front.append(result_point(candidate))
    return sorted(
        front,
        key=lambda item: (
            item["timed_seeding_time_per_event_ms"],
            -item["timed_ambiguity_particle_efficiency"],
            item["candidate"],
        ),
    )


def promising_results(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [attempt for attempt in attempts if attempt["state"] == "completed"]
    genesis_attempts = [attempt for attempt in completed if attempt["classification"] == "baseline"]
    latest_genesis = max(genesis_attempts, key=lambda item: item["started_at"], default=None)
    best_seeding = min(
        completed,
        key=lambda item: (item["timed_seeding_time_per_event_ms"], item["candidate"]),
        default=None,
    )
    best_efficiency = max(
        completed,
        key=lambda item: (item["timed_ambiguity_particle_efficiency"], item["candidate"]),
        default=None,
    )
    best_seeding_result = result_point(best_seeding) if best_seeding is not None else None
    if best_seeding_result is not None:
        if latest_genesis is None:
            best_seeding_result["delta_vs_genesis_ms"] = None
            best_seeding_result["percentage_vs_genesis"] = None
        else:
            baseline_time = latest_genesis["timed_seeding_time_per_event_ms"]
            delta = best_seeding["timed_seeding_time_per_event_ms"] - baseline_time
            best_seeding_result["delta_vs_genesis_ms"] = delta
            best_seeding_result["percentage_vs_genesis"] = (
                delta / baseline_time * 100 if baseline_time else None
            )
    return {
        "latest_genesis": result_point(latest_genesis) if latest_genesis is not None else None,
        "best_seeding": best_seeding_result,
        "best_ambiguity_efficiency": (
            result_point(best_efficiency) if best_efficiency is not None else None
        ),
        "pareto_front": pareto_front(attempts),
    }


def calculate_eta(
    completed_durations: list[float],
    attempts_remaining: int,
    now: datetime,
    *,
    current_started_at: datetime | None = None,
    current_is_pending: bool = False,
    blocked: bool = False,
) -> dict[str, Any]:
    """Estimate remaining time from a robust median, never from scientific timing."""

    valid_durations = [
        float(value) for value in completed_durations if finite_number(value) and value >= 0
    ]
    if attempts_remaining <= 0:
        return {
            "median_seconds": median(valid_durations) if valid_durations else None,
            "sample_count": len(valid_durations),
            "remaining_seconds": 0.0,
            "expected_finish_at": isoformat(now),
            "basis": "Campaign attempt targets are complete.",
        }
    if blocked:
        return {
            "median_seconds": median(valid_durations) if valid_durations else None,
            "sample_count": len(valid_durations),
            "remaining_seconds": None,
            "expected_finish_at": None,
            "basis": "Unavailable while the campaign is blocked.",
        }
    if len(valid_durations) < ETA_MINIMUM_SAMPLES:
        return {
            "median_seconds": median(valid_durations) if valid_durations else None,
            "sample_count": len(valid_durations),
            "remaining_seconds": None,
            "expected_finish_at": None,
            "basis": (
                f"Unavailable until {ETA_MINIMUM_SAMPLES} completed attempt durations exist "
                f"({len(valid_durations)} available)."
            ),
        }

    median_seconds = float(median(valid_durations))
    remaining_seconds = attempts_remaining * median_seconds
    deducted = False
    if current_is_pending and current_started_at is not None:
        current_elapsed = max((now - current_started_at).total_seconds(), 0.0)
        remaining_seconds = max(median_seconds - current_elapsed, 0.0)
        remaining_seconds += max(attempts_remaining - 1, 0) * median_seconds
        deducted = True
    basis = f"Median of {len(valid_durations)} completed attempts"
    basis += "; current attempt elapsed time deducted." if deducted else "."
    return {
        "median_seconds": median_seconds,
        "sample_count": len(valid_durations),
        "remaining_seconds": remaining_seconds,
        "expected_finish_at": isoformat(now + timedelta(seconds=remaining_seconds)),
        "basis": basis,
    }


def latest_candidate_state(attempts: list[dict[str, Any]], candidate: str) -> str | None:
    matches = [attempt for attempt in attempts if attempt["candidate"] == candidate]
    return matches[-1]["state"] if matches else None


def build_status(
    live_state: dict[str, Any],
    attempts: list[dict[str, Any]],
    generated_at: datetime,
    active_commit: str | None,
) -> dict[str, Any]:
    generated_at = generated_at.astimezone(timezone.utc)
    campaign_start = parse_instant(live_state["campaign"]["started_at"], "campaign.started_at")
    if generated_at < campaign_start:
        raise StatusError("generated_at cannot precede campaign.started_at")
    if active_commit is not None and not FULL_COMMIT_SHA.fullmatch(active_commit.lower()):
        raise StatusError("active commit must be a full Git SHA")

    non_baseline = [attempt for attempt in attempts if attempt["classification"] != "baseline"]
    completed = [attempt for attempt in non_baseline if attempt["state"] == "completed"]
    attempted_candidates = {attempt["candidate"] for attempt in non_baseline}
    current = live_state["current_attempt"]
    if current is not None and current["classification"] != "baseline":
        attempted_candidates.add(current["candidate"])
    metadata = {
        item["candidate"]: item for item in live_state["attempt_metadata"]
    }
    if current is not None and current["candidate"] != "Genesis":
        metadata[current["candidate"]] = current
    structural_attempts = sum(
        1
        for candidate in attempted_candidates
        if metadata.get(candidate, {}).get("classification") == "structural"
    )
    micro_attempts = sum(
        1
        for candidate in attempted_candidates
        if metadata.get(candidate, {}).get("classification") == "micro"
    )
    completed_remaining = max(COMPLETED_ATTEMPT_TARGET - len(completed), 0)
    structural_remaining = max(STRUCTURAL_ATTEMPT_TARGET - structural_attempts, 0)
    attempts_remaining = max(completed_remaining, structural_remaining)

    current_is_pending = False
    current_started_at = None
    if current is not None:
        if current["started_at"] is not None:
            current_started_at = parse_instant(
                current["started_at"], "current_attempt.started_at"
            )
        current_has_evidence = any(
            attempt["candidate"] == current["candidate"]
            and (
                current_started_at is None
                or parse_instant(attempt["started_at"], "attempt.started_at")
                >= current_started_at
            )
            for attempt in attempts
        )
        current_is_pending = (
            current["state"] in {"queued", "running"} and not current_has_evidence
        )
    eta = calculate_eta(
        [attempt["duration_seconds"] for attempt in completed if attempt["duration_seconds"] is not None],
        attempts_remaining,
        generated_at,
        current_started_at=current_started_at,
        current_is_pending=current_is_pending,
        blocked=bool(live_state["blockers"])
        or bool(current and current["state"] == "blocked"),
    )

    failures = [
        {
            "candidate": attempt["candidate"],
            "message": attempt["outcome"],
            "record_url": attempt["links"]["record"],
        }
        for attempt in attempts
        if attempt["state"] == "failed"
    ]
    branch = live_state["campaign"]["branch"]
    status = {
        "$schema": STATUS_SCHEMA_URL,
        "schema_version": STATUS_SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "generated_at": isoformat(generated_at),
        "stale_after_seconds": STALE_AFTER_SECONDS,
        "repository": {
            "url": REPOSITORY_URL,
            "snapshot_path": "campaign-status.json",
        },
        "campaign": {
            **live_state["campaign"],
            "targets": {
                "completed_attempts": COMPLETED_ATTEMPT_TARGET,
                "structural_attempts": STRUCTURAL_ATTEMPT_TARGET,
                "micro_optimization_cap": MICRO_OPTIMIZATION_CAP,
            },
        },
        "current_attempt": current,
        "progress": {
            "completed_attempts": len(completed),
            "structural_attempts": structural_attempts,
            "micro_optimizations": micro_attempts,
            "elapsed_seconds": (generated_at - campaign_start).total_seconds(),
            "median_completed_attempt_duration_seconds": eta["median_seconds"],
            "estimated_remaining_seconds": eta["remaining_seconds"],
            "expected_finish_at": eta["expected_finish_at"],
            "eta_sample_count": eta["sample_count"],
            "eta_basis": eta["basis"],
        },
        "promising_results": promising_results(attempts),
        "attempts": attempts,
        "blockers": [{"message": message} for message in live_state["blockers"]],
        "failures": failures,
        "links": {
            "campaign_branch": f"{REPOSITORY_URL}/tree/{quote(branch, safe='/')}",
            "pull_request": live_state["pull_request_url"],
            "active_commit": commit_url(active_commit),
        },
    }
    validate_status(status)
    return status


def validate_result(value: Any, field: str, *, best_seeding: bool = False) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise StatusError(f"{field} must be an object or null")
    for key in (
        "candidate",
        "timed_seeding_time_per_event_ms",
        "timed_ambiguity_particle_efficiency",
        "started_at",
        "links",
    ):
        if key not in value:
            raise StatusError(f"{field} is missing {key}")
    if not finite_number(value["timed_seeding_time_per_event_ms"]):
        raise StatusError(f"{field} has invalid seeding time")
    if not finite_number(value["timed_ambiguity_particle_efficiency"]):
        raise StatusError(f"{field} has invalid efficiency")
    parse_instant(value["started_at"], f"{field}.started_at")
    if best_seeding:
        for key in ("delta_vs_genesis_ms", "percentage_vs_genesis"):
            if key not in value or (
                value[key] is not None and not finite_number(value[key])
            ):
                raise StatusError(f"{field}.{key} is invalid")


def validate_status(value: Any) -> None:
    """Validate generated snapshots without requiring an external schema package."""

    if not isinstance(value, dict):
        raise StatusError("campaign status must be an object")
    required = {
        "$schema",
        "schema_version",
        "protocol_id",
        "generated_at",
        "stale_after_seconds",
        "repository",
        "campaign",
        "current_attempt",
        "progress",
        "promising_results",
        "attempts",
        "blockers",
        "failures",
        "links",
    }
    if set(value) != required:
        raise StatusError("campaign status fields do not match schema v1")
    if value["schema_version"] != STATUS_SCHEMA_VERSION:
        raise StatusError("campaign status schema version is unsupported")
    if value["protocol_id"] != PROTOCOL_ID:
        raise StatusError("campaign status protocol is incompatible")
    parse_instant(value["generated_at"], "generated_at")
    if not isinstance(value["stale_after_seconds"], int) or value["stale_after_seconds"] < 60:
        raise StatusError("stale_after_seconds must be at least 60")
    campaign = value["campaign"]
    if not isinstance(campaign, dict) or "targets" not in campaign:
        raise StatusError("campaign is invalid")
    validate_ref(campaign.get("branch"))
    parse_instant(campaign.get("started_at"), "campaign.started_at")
    targets = campaign["targets"]
    if targets != {
        "completed_attempts": COMPLETED_ATTEMPT_TARGET,
        "structural_attempts": STRUCTURAL_ATTEMPT_TARGET,
        "micro_optimization_cap": MICRO_OPTIMIZATION_CAP,
    }:
        raise StatusError("campaign targets are not the controlled defaults")
    progress = value["progress"]
    if not isinstance(progress, dict):
        raise StatusError("progress must be an object")
    for key in (
        "completed_attempts",
        "structural_attempts",
        "micro_optimizations",
        "elapsed_seconds",
        "eta_sample_count",
    ):
        if not finite_number(progress.get(key)) or progress[key] < 0:
            raise StatusError(f"progress.{key} is invalid")
    for key in (
        "median_completed_attempt_duration_seconds",
        "estimated_remaining_seconds",
    ):
        if progress.get(key) is not None and (
            not finite_number(progress[key]) or progress[key] < 0
        ):
            raise StatusError(f"progress.{key} is invalid")
    if progress.get("expected_finish_at") is not None:
        parse_instant(progress["expected_finish_at"], "progress.expected_finish_at")
    if not isinstance(progress.get("eta_basis"), str):
        raise StatusError("progress.eta_basis is invalid")
    promising = value["promising_results"]
    if not isinstance(promising, dict) or set(promising) != {
        "latest_genesis",
        "best_seeding",
        "best_ambiguity_efficiency",
        "pareto_front",
    }:
        raise StatusError("promising_results is invalid")
    validate_result(promising["latest_genesis"], "promising_results.latest_genesis")
    validate_result(
        promising["best_seeding"],
        "promising_results.best_seeding",
        best_seeding=True,
    )
    validate_result(
        promising["best_ambiguity_efficiency"],
        "promising_results.best_ambiguity_efficiency",
    )
    if not isinstance(promising["pareto_front"], list):
        raise StatusError("promising_results.pareto_front must be an array")
    for index, item in enumerate(promising["pareto_front"]):
        validate_result(item, f"promising_results.pareto_front[{index}]")
    if not isinstance(value["attempts"], list):
        raise StatusError("attempts must be an array")
    for index, attempt in enumerate(value["attempts"]):
        if not isinstance(attempt, dict):
            raise StatusError(f"attempts[{index}] must be an object")
        if attempt.get("classification") not in CLASSIFICATIONS:
            raise StatusError(f"attempts[{index}].classification is invalid")
        if attempt.get("state") not in {"completed", "failed"}:
            raise StatusError(f"attempts[{index}].state is invalid")
        if attempt.get("duration_seconds") is not None and (
            not finite_number(attempt["duration_seconds"])
            or attempt["duration_seconds"] < 0
        ):
            raise StatusError(f"attempts[{index}].duration_seconds is invalid")
        for objective in (
            "timed_seeding_time_per_event_ms",
            "timed_ambiguity_particle_efficiency",
        ):
            if attempt.get(objective) is not None and not finite_number(attempt[objective]):
                raise StatusError(f"attempts[{index}].{objective} is invalid")
    for field in ("blockers", "failures"):
        if not isinstance(value[field], list):
            raise StatusError(f"{field} must be an array")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def git_output(repository_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise StatusError(result.stderr.strip() or "could not inspect the Git checkout")
    return result.stdout.strip()


def git_head(repository_root: Path) -> str:
    commit = git_output(repository_root, "rev-parse", "HEAD").lower()
    if not FULL_COMMIT_SHA.fullmatch(commit):
        raise StatusError("could not determine active Git commit")
    return commit


def git_branch(repository_root: Path) -> str:
    branch = git_output(repository_root, "branch", "--show-current")
    if not branch:
        raise StatusError("campaign status must be generated from a branch, not detached HEAD")
    return validate_ref(branch)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--generated-at",
        help="ISO timestamp override for deterministic testing (default: current UTC time)",
    )
    parser.add_argument("--repository-root", type=Path, default=PROJECT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw_state = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"error: cannot read campaign status input: {error}") from error
    try:
        live_state = validate_live_state(raw_state)
        generated_at = (
            parse_instant(args.generated_at, "generated_at")
            if args.generated_at
            else datetime.now(timezone.utc)
        )
        repository_root = args.repository_root.resolve()
        branch = git_branch(repository_root)
        if branch != live_state["campaign"]["branch"]:
            raise StatusError(
                "input campaign branch does not match the checked-out branch: "
                f"{branch}"
            )
        attempts = load_attempts(args.records.resolve(), live_state)
        status = build_status(
            live_state,
            attempts,
            generated_at,
            git_head(repository_root),
        )
        atomic_write_json(args.output.resolve(), status)
    except StatusError as error:
        raise SystemExit(f"error: {error}") from error
    print(f"wrote {args.output.resolve()}")
    print(f"included {len(attempts)} protocol-compatible Development record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
