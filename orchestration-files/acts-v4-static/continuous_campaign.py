#!/usr/bin/env python3
"""Own the isolated continuous revision-2 owned-static v4 campaign lifecycle."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ORCHESTRATION_ROOT = Path(__file__).resolve().parent.parent
if str(ORCHESTRATION_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATION_ROOT))

from campaign_control import observe_stop_request  # noqa: E402
from campaign_status import (  # noqa: E402
    build_status as build_v3_status,
    validate_live_state as validate_v3_live_state,
)
from schema import (  # noqa: E402
    ACTS_COMMIT,
    CANONICAL_PROTOCOL_ID,
    PILOT_PROTOCOL_REVISION,
    atomic_write_json,
    canonical_json_bytes,
    sha256_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / "orchestration-files" / "acts-v4-continuous-campaign"
DEFAULT_STATE = DEFAULT_ROOT / "campaign.json"
DEFAULT_STATUS = DEFAULT_ROOT / "status.json"
DEFAULT_BRIDGE_INPUT = (
    PROJECT_ROOT / "orchestration-files" / "campaign-status-input.json"
)
DEFAULT_BRIDGE_STATUS = PROJECT_ROOT / "orchestration-files" / "campaign-status.json"

STATE_SCHEMA = "acts-v4-owned-static-continuous-campaign-v1"
STATUS_SCHEMA = "acts-v4-owned-static-continuous-status-v1"
RECORD_SCHEMA = "acts-v4-owned-static-development-record-v2"
PLATFORM_COMMIT = "c72c1a32d61858eaad05b0f6f19c712d0c53f2ba"
SCIENTIFIC_GENESIS_COMMIT = "5ed3b47329ceda4edaab48b1efc3c5635f361a30"
DATASET_ID = (
    "acts-seeding-v4-owned-static-"
    "a05ae8663452d52dc2b90e2fa5372091a2cb04feb8cce86646da9f6ccbc2f3fb"
)
DATASET_MANIFEST_SHA256 = (
    "13274b01178462f1375eebd0cba283551a5ca04ec9724aa189aaf33e4e2f5666"
)
DATASET_PAYLOAD_SHA256 = (
    "534c14c0cbc2f37aecd091d879c168348d2c2e2cc4f9719c3580bbd54dc6d510"
)
QUALIFICATION_EVIDENCE_SHA256 = (
    "ed16fef43f1b6818e52cf6b0493d9c786a70444d212e7ab521eadd03d4b37237"
)
BLOCK = ("major", "major", "minor", "combination")
CATEGORIES = ("major", "minor", "combination")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CAMPAIGN_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,126}[a-z0-9]$")


class ContinuousCampaignError(ValueError):
    """The isolated static-v4 campaign state or evidence is unsafe."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ContinuousCampaignError(f"{field} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContinuousCampaignError(
            f"{field} must be an ISO 8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise ContinuousCampaignError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_keys(value: Any, field: str, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContinuousCampaignError(f"{field} must be an object")
    if set(value) != expected:
        raise ContinuousCampaignError(
            f"{field} fields differ: missing={sorted(expected - set(value))}, "
            f"extra={sorted(set(value) - expected)}"
        )
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContinuousCampaignError(f"{field} must be a lowercase SHA-256")
    return value


def _canonical_load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContinuousCampaignError(
            f"cannot read canonical JSON {path}: {error}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ContinuousCampaignError(f"JSON is not canonical: {path}")
    return value


def _resolve_evidence_path(path_value: str, repository_root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else repository_root / path


def _proposal(
    value: Any, *, slot: int, candidate: str, classification: str
) -> dict[str, Any]:
    required = {
        "schema_version",
        "candidate",
        "slot",
        "classification",
        "mechanism_key",
        "mechanism_family",
        "implementation_commit",
        "hypothesis",
        "falsifier",
        "predicted_directions",
        "expected_hot_path",
        "changed_symbols",
        "intended_files",
        "physics_invariants",
        "novelty_reason",
        "source_references",
        "derives_from",
        "combination_provenance",
    }
    proposal = _require_keys(value, "record.proposal", required)
    if (
        proposal["schema_version"] != "1.0.0"
        or proposal["slot"] != slot
        or proposal["candidate"] != candidate
        or proposal["classification"] != classification
    ):
        raise ContinuousCampaignError("record proposal identity differs from its slot")
    commit = proposal["implementation_commit"]
    if not isinstance(commit, str) or _GIT_SHA.fullmatch(commit) is None:
        raise ContinuousCampaignError(
            "record proposal implementation commit is invalid"
        )
    mechanism = proposal["mechanism_key"]
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ContinuousCampaignError("record proposal mechanism key is invalid")
    files = proposal["intended_files"]
    if (
        not isinstance(files, list)
        or not files
        or files != sorted(set(files))
        or any(
            not isinstance(item, str)
            or not item.startswith("optimization-files/")
            or ".." in Path(item).parts
            for item in files
        )
    ):
        raise ContinuousCampaignError("record proposal intended files are invalid")
    invariants = proposal["physics_invariants"]
    if (
        not isinstance(invariants, list)
        or not invariants
        or not all(isinstance(item, str) and item.strip() for item in invariants)
    ):
        raise ContinuousCampaignError("record proposal physics invariants are missing")
    references = proposal["source_references"]
    if not isinstance(references, list) or not references:
        raise ContinuousCampaignError("record proposal is not source-grounded")
    return proposal


def _validate_record(path: Path, attempt: dict[str, Any]) -> dict[str, Any]:
    record = _canonical_load(path)
    claimed = record.get("record_sha256")
    unhashed = dict(record)
    unhashed.pop("record_sha256", None)
    if (
        not isinstance(claimed, str)
        or hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest() != claimed
    ):
        raise ContinuousCampaignError(f"record self-hash mismatch: {path}")
    if (
        record.get("schema") != RECORD_SCHEMA
        or record.get("protocol_id") != CANONICAL_PROTOCOL_ID
        or record.get("protocol_revision") != PILOT_PROTOCOL_REVISION
        or record.get("dataset_id") != DATASET_ID
        or record.get("category") != "Development"
        or record.get("scientific_processes") != 1
        or record.get("baseline") is not False
    ):
        raise ContinuousCampaignError(
            f"record is not exact revision-2 owned-static Development evidence: {path}"
        )
    if record.get("status") not in {"passed", "invalid"}:
        raise ContinuousCampaignError(f"record status is unsupported: {path}")
    slot = attempt["slot"]
    candidate = attempt["candidate"]
    classification = attempt["classification"]
    if (
        record.get("slot") != slot
        or record.get("candidate_name") != candidate
        or record.get("classification") != classification
        or record.get("mechanism_key") != attempt["mechanism_key"]
        or record.get("implementation_commit") != attempt["implementation_commit"]
    ):
        raise ContinuousCampaignError(
            f"record differs from durable attempt identity: {path}"
        )
    proposal = _proposal(
        record.get("proposal"),
        slot=slot,
        candidate=candidate,
        classification=classification,
    )
    proposal_hash = hashlib.sha256(canonical_json_bytes(proposal)).hexdigest()
    if (
        proposal_hash != record.get("proposal_sha256")
        or proposal_hash != attempt["proposal_sha256"]
        or claimed != attempt["record_sha256"]
        or sha256_file(path) != attempt["record_sha256"]
    ):
        # A canonical self-hashed record's byte hash includes the self-hash and is
        # distinct. Durable state binds the scientific self-hash, while the file
        # remains canonical and immutable.
        if (
            proposal_hash != record.get("proposal_sha256")
            or proposal_hash != attempt["proposal_sha256"]
            or claimed != attempt["record_sha256"]
        ):
            raise ContinuousCampaignError(
                f"record or proposal binding mismatch: {path}"
            )
    result = record.get("result")
    if not isinstance(result, dict):
        raise ContinuousCampaignError(f"record result is missing: {path}")
    if (
        result.get("protocol_id") != CANONICAL_PROTOCOL_ID
        or result.get("protocol_revision") != PILOT_PROTOCOL_REVISION
        or result.get("dataset_id") != DATASET_ID
        or result.get("events") != 50
        or result.get("threads") != 1
    ):
        raise ContinuousCampaignError(
            f"record result protocol identity differs: {path}"
        )
    if record["status"] == "passed":
        if (
            result.get("process_exit_status") != 0
            or result.get("fpe", {}).get("observed_unmasked") != 0
            or result.get("loaded_acts_dso_closure", {}).get("complete") is not True
            or len(result.get("input_event_hashes", [])) != 50
            or record.get("latency", {}).get("static_process_target_passed") is not True
            or record.get("latency", {}).get("queue_to_record_target_passed")
            is not True
        ):
            raise ContinuousCampaignError(
                f"passed record lacks hard-validity evidence: {path}"
            )
    return record


def _validate_campaign(value: Any) -> dict[str, Any]:
    fields = {
        "name",
        "branch",
        "campaign_id",
        "control_id",
        "started_at",
        "platform_commit",
        "scientific_genesis_commit",
        "acts_commit",
        "protocol_id",
        "protocol_revision",
        "dataset_id",
        "development_only",
        "evaluation_authorized",
    }
    campaign = _require_keys(value, "campaign", fields)
    if campaign["platform_commit"] != PLATFORM_COMMIT:
        raise ContinuousCampaignError("campaign platform commit identity mismatch")
    if campaign["scientific_genesis_commit"] != SCIENTIFIC_GENESIS_COMMIT:
        raise ContinuousCampaignError(
            "campaign scientific Genesis must remain the dataset-bound project commit"
        )
    if campaign["acts_commit"] != ACTS_COMMIT:
        raise ContinuousCampaignError("campaign ACTS commit identity mismatch")
    if (
        campaign["protocol_id"] != CANONICAL_PROTOCOL_ID
        or campaign["protocol_revision"] != PILOT_PROTOCOL_REVISION
        or campaign["dataset_id"] != DATASET_ID
    ):
        raise ContinuousCampaignError(
            "campaign revision-2 static protocol identity mismatch"
        )
    if (
        campaign["development_only"] is not True
        or campaign["evaluation_authorized"] is not False
    ):
        raise ContinuousCampaignError("campaign must remain Development-only")
    if (
        not isinstance(campaign["campaign_id"], str)
        or _CAMPAIGN_ID.fullmatch(campaign["campaign_id"]) is None
    ):
        raise ContinuousCampaignError("campaign id is invalid")
    _sha(campaign["control_id"], "campaign.control_id")
    _parse_time(campaign["started_at"], "campaign.started_at")
    if not isinstance(campaign["branch"], str) or not campaign["branch"].startswith(
        "fm/"
    ):
        raise ContinuousCampaignError(
            "campaign branch is outside the authorized task branch"
        )
    return campaign


def _validate_control(value: Any) -> dict[str, Any]:
    control = _require_keys(
        value,
        "control",
        {"state", "request", "observed_at", "consumed_at", "completed_at"},
    )
    if control["state"] not in {"open", "requested", "consumed", "completed"}:
        raise ContinuousCampaignError("campaign control state is invalid")
    if control["state"] == "open":
        if any(
            control[key] is not None
            for key in ("request", "observed_at", "consumed_at", "completed_at")
        ):
            raise ContinuousCampaignError(
                "open control state contains terminal evidence"
            )
    else:
        if not isinstance(control["request"], dict) or control["observed_at"] is None:
            raise ContinuousCampaignError(
                "observed control state lacks authenticated request"
            )
        _parse_time(control["observed_at"], "control.observed_at")
    if control["state"] in {"consumed", "completed"}:
        _parse_time(control["consumed_at"], "control.consumed_at")
    if control["state"] == "completed":
        _parse_time(control["completed_at"], "control.completed_at")
    return control


def validate_state(
    value: Any, *, repository_root: Path = PROJECT_ROOT
) -> dict[str, Any]:
    fields = {
        "schema",
        "campaign",
        "dataset",
        "calibration",
        "current_attempt",
        "attempts",
        "corrections",
        "control",
        "scheduler",
        "pull_request_url",
        "restoration",
    }
    state = _require_keys(value, "campaign state", fields)
    if state["schema"] != STATE_SCHEMA:
        raise ContinuousCampaignError("static-v4 continuous campaign schema mismatch")
    _validate_campaign(state["campaign"])
    dataset = _require_keys(
        state["dataset"],
        "dataset",
        {
            "publication_path",
            "manifest_sha256",
            "payload_sha256",
            "qualification_evidence_sha256",
        },
    )
    if (
        dataset["publication_path"]
        != f"/storage/thomaaks/acts-v4-owned-static/{DATASET_ID}"
        or dataset["manifest_sha256"] != DATASET_MANIFEST_SHA256
        or dataset["payload_sha256"] != DATASET_PAYLOAD_SHA256
        or dataset["qualification_evidence_sha256"] != QUALIFICATION_EVIDENCE_SHA256
    ):
        raise ContinuousCampaignError("canonical dataset publication identity mismatch")
    calibration = state["calibration"]
    if calibration is not None:
        calibration = _require_keys(
            calibration, "calibration", {"path", "sha256", "runs", "valid"}
        )
        _sha(calibration["sha256"], "calibration.sha256")
        if calibration["runs"] != 5 or calibration["valid"] is not True:
            raise ContinuousCampaignError(
                "campaign calibration is not five new valid runs"
            )
    if state["current_attempt"] is not None:
        current = _require_keys(
            state["current_attempt"],
            "current_attempt",
            {"slot", "candidate", "classification", "state", "scheduling", "queued_at"},
        )
        if current["slot"] != len(state["attempts"]) + 1:
            raise ContinuousCampaignError(
                "current attempt slot is not the next immutable slot"
            )
        if current["classification"] != BLOCK[(current["slot"] - 1) % 4]:
            raise ContinuousCampaignError(
                "current attempt violates deterministic block order"
            )
        if current["state"] not in {"queued", "preparing", "running", "recording"}:
            raise ContinuousCampaignError("current attempt state is invalid")
        if current["scheduling"] not in {"ordinary", "finalization"}:
            raise ContinuousCampaignError(
                "current attempt scheduling purpose is invalid"
            )
        _parse_time(current["queued_at"], "current_attempt.queued_at")
    attempts = state["attempts"]
    if not isinstance(attempts, list):
        raise ContinuousCampaignError("attempts must be an array")
    names: set[str] = set()
    mechanisms: set[str] = set()
    normalized_attempts = []
    for index, attempt_value in enumerate(attempts, 1):
        attempt = _require_keys(
            attempt_value,
            f"attempts[{index - 1}]",
            {
                "slot",
                "candidate",
                "classification",
                "mechanism_key",
                "implementation_commit",
                "proposal_path",
                "proposal_sha256",
                "record_path",
                "record_sha256",
                "state",
                "scheduling",
            },
        )
        if (
            attempt["slot"] != index
            or attempt["classification"] != BLOCK[(index - 1) % 4]
        ):
            raise ContinuousCampaignError(
                "attempt history violates deterministic 2:1:1 block order"
            )
        if attempt["state"] != "recorded" or attempt["scheduling"] not in {
            "ordinary",
            "finalization",
        }:
            raise ContinuousCampaignError(
                "attempt is not an immutable recorded transaction"
            )
        if attempt["candidate"] in names or attempt["mechanism_key"] in mechanisms:
            raise ContinuousCampaignError(
                "candidate names and mechanism keys must be globally unique"
            )
        names.add(attempt["candidate"])
        mechanisms.add(attempt["mechanism_key"])
        if (
            not isinstance(attempt["implementation_commit"], str)
            or _GIT_SHA.fullmatch(attempt["implementation_commit"]) is None
        ):
            raise ContinuousCampaignError("attempt implementation commit is invalid")
        _sha(attempt["proposal_sha256"], "attempt.proposal_sha256")
        _sha(attempt["record_sha256"], "attempt.record_sha256")
        record_path = _resolve_evidence_path(attempt["record_path"], repository_root)
        _validate_record(record_path, attempt)
        normalized_attempts.append(copy.deepcopy(attempt))
    control = _validate_control(state["control"])
    scheduler = _require_keys(
        state["scheduler"], "scheduler", {"state", "final_targets", "blocker"}
    )
    if scheduler["state"] not in {"running", "finishing", "blocked", "completed"}:
        raise ContinuousCampaignError("scheduler state is invalid")
    if control["state"] in {"consumed", "completed"}:
        targets = _require_keys(
            scheduler["final_targets"], "scheduler.final_targets", set(CATEGORIES)
        )
        if (
            targets["major"] != 2 * targets["minor"]
            or targets["minor"] != targets["combination"]
            or targets["minor"] < 1
        ):
            raise ContinuousCampaignError(
                "final targets are not a positive exact 2:1:1 composition"
            )
    elif scheduler["final_targets"] is not None:
        raise ContinuousCampaignError("open scheduler cannot predeclare a final total")
    if not isinstance(state["corrections"], list):
        raise ContinuousCampaignError("corrections must be an array")
    normalized = copy.deepcopy(state)
    normalized["attempts"] = normalized_attempts
    return normalized


def completed_counts(state: dict[str, Any]) -> dict[str, int]:
    return {
        category: sum(
            attempt["classification"] == category for attempt in state["attempts"]
        )
        for category in CATEGORIES
    }


def _targets_for_completed(completed: int) -> dict[str, int]:
    blocks = max(1, math.ceil(completed / len(BLOCK)))
    return {"major": 2 * blocks, "minor": blocks, "combination": blocks}


def next_category(
    completed: int,
    *,
    control_state: str,
    final_targets: dict[str, int] | None,
) -> str | None:
    if control_state == "completed":
        return None
    if control_state == "consumed":
        if final_targets is None:
            raise ContinuousCampaignError("consumed stop lacks final targets")
        if completed >= sum(final_targets.values()):
            return None
    elif control_state not in {"open", "requested"}:
        raise ContinuousCampaignError("unsupported control state")
    return BLOCK[completed % len(BLOCK)]


def _bridge_live(state: dict[str, Any]) -> dict[str, Any]:
    control = copy.deepcopy(state["control"])
    scheduler_state = {
        "running": "running",
        "finishing": "finishing",
        "blocked": "blocked",
        "completed": "finishing",
    }[state["scheduler"]["state"]]
    targets = state["scheduler"]["final_targets"]
    bridge_targets = None
    if targets is not None:
        bridge_targets = {
            "completed_candidates": sum(targets.values()),
            "major_candidates": targets["major"],
            "minor_candidates": targets["minor"],
            "combination_candidates": targets["combination"],
        }
    return {
        "schema_version": "1.1.0",
        "campaign": {
            "name": state["campaign"]["name"] + " control bridge",
            "branch": state["campaign"]["branch"],
            "phase": "See exact revision-2 owned-static sidecar status",
            "started_at": state["campaign"]["started_at"],
            "mode": "continuous",
            "campaign_id": state["campaign"]["campaign_id"],
            "control_id": state["campaign"]["control_id"],
            "genesis_commit": PLATFORM_COMMIT,
            "targets": {
                "major_percentage": 50,
                "minor_percentage": 25,
                "combination_percentage": 25,
            },
        },
        "current_attempt": None,
        "attempt_metadata": [],
        "blockers": (
            [state["scheduler"]["blocker"]] if state["scheduler"]["blocker"] else []
        ),
        "pull_request_url": state["pull_request_url"],
        "control": control,
        "scheduler": {
            "state": scheduler_state,
            "combination_readiness": None,
            "final_targets": bridge_targets,
            "blocker": state["scheduler"]["blocker"],
        },
    }


def observe_stop(
    state: dict[str, Any], issues: list[dict[str, Any]], observed_at: datetime
) -> tuple[dict[str, Any], bool]:
    validated = validate_state(state)
    bridge, changed = observe_stop_request(_bridge_live(validated), issues, observed_at)
    if not changed:
        return state, False
    updated = copy.deepcopy(state)
    updated["control"] = bridge["control"]
    return validate_state(updated), True


def consume_stop(state: dict[str, Any], consumed_at: datetime) -> dict[str, Any]:
    validated = validate_state(state)
    if validated["control"]["state"] == "consumed":
        return state
    if validated["control"]["state"] != "requested":
        raise ContinuousCampaignError(
            "no authenticated stop request is ready to consume"
        )
    if validated["current_attempt"] is not None:
        raise ContinuousCampaignError(
            "active candidate must be recorded before stop consumption"
        )
    updated = copy.deepcopy(state)
    updated["control"]["state"] = "consumed"
    updated["control"]["consumed_at"] = _iso(consumed_at)
    updated["scheduler"].update(
        {
            "state": "finishing",
            "final_targets": _targets_for_completed(len(validated["attempts"])),
            "blocker": None,
        }
    )
    return validate_state(updated)


def _genesis_median_peak_rss(
    calibration: dict[str, Any], repository_root: Path
) -> int | None:
    expected_timings = sorted(calibration.get("genesis_per_event_nanoseconds", []))
    if len(expected_timings) != 5:
        return None
    groups: dict[str, list[tuple[int, int]]] = {}
    for path in repository_root.glob("records/Development/*-Genesis-*/summary.json"):
        try:
            record = _canonical_load(path)
        except ContinuousCampaignError:
            continue
        result = record.get("result")
        resources = result.get("resources") if isinstance(result, dict) else None
        timing = result.get("timing") if isinstance(result, dict) else None
        if (
            record.get("schema") != RECORD_SCHEMA
            or record.get("candidate_name") != "Genesis"
            or record.get("status") != "passed"
            or record.get("protocol_id") != CANONICAL_PROTOCOL_ID
            or record.get("protocol_revision") != PILOT_PROTOCOL_REVISION
            or record.get("dataset_id") != DATASET_ID
            or record.get("implementation_commit") != SCIENTIFIC_GENESIS_COMMIT
            or not isinstance(resources, dict)
            or not isinstance(timing, dict)
            or not isinstance(resources.get("peak_rss_kb"), int)
            or not isinstance(timing.get("per_event_nanoseconds"), int)
        ):
            continue
        group = path.parent.name.rsplit("-Genesis-", 1)[0]
        groups.setdefault(group, []).append(
            (timing["per_event_nanoseconds"], resources["peak_rss_kb"])
        )
    matches = [
        values
        for values in groups.values()
        if len(values) == 5
        and sorted(timing for timing, _ in values) == expected_timings
    ]
    if len(matches) != 1:
        return None
    values = sorted(rss for _, rss in matches[0])
    return values[len(values) // 2]


def _record_projection(record: dict[str, Any], record_path: str) -> dict[str, Any]:
    result = record["result"]
    return {
        "slot": record["slot"],
        "record_path": record_path,
        "candidate": record["candidate_name"],
        "classification": record["classification"],
        "status": record["status"],
        "mechanism_key": record["mechanism_key"],
        "implementation_commit": record["implementation_commit"],
        "proposal": record["proposal"],
        "proposal_sha256": record["proposal_sha256"],
        "record_sha256": record["record_sha256"],
        "scientific_classification": record["scientific_classification"],
        "timing": result.get("timing"),
        "stats": result.get("stats"),
        "rates": result.get("rates"),
        "resources": result.get("resources"),
        "latency": record.get("latency"),
        "input_event_hashes": result.get("input_event_hashes"),
        "truth_denominator_hashes": record.get("truth_denominator_hashes"),
        "loaded_acts_dso_closure": result.get("loaded_acts_dso_closure"),
        "loaded_dso_manifest_sha256": result.get("identities", {}).get(
            "loaded_dso_manifest_sha256"
        ),
        "candidate_binding": result.get("candidate_binding"),
        "corrections": record.get("corrections", []),
    }


def build_status(
    state: dict[str, Any],
    generated_at: datetime,
    commit: str,
    *,
    repository_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    validated = validate_state(state, repository_root=repository_root)
    counts = completed_counts(validated)
    total = len(validated["attempts"])
    calibration_value = None
    if validated["calibration"] is not None:
        path = _resolve_evidence_path(validated["calibration"]["path"], repository_root)
        calibration_value = (
            _canonical_load(path) if path.is_file() else validated["calibration"]
        )
        median_peak_rss = _genesis_median_peak_rss(calibration_value, repository_root)
        if median_peak_rss is not None:
            calibration_value["median_peak_rss_kb"] = median_peak_rss
    return {
        "schema": STATUS_SCHEMA,
        "generated_at": _iso(generated_at),
        "commit": commit,
        "campaign": validated["campaign"],
        "dataset": validated["dataset"],
        "calibration": calibration_value,
        "control": validated["control"],
        "scheduler": {
            **validated["scheduler"],
            "next_category": next_category(
                total,
                control_state=validated["control"]["state"],
                final_targets=validated["scheduler"]["final_targets"],
            ),
        },
        "current_attempt": validated["current_attempt"],
        "composition": {
            "block_order": list(BLOCK),
            "counts": counts,
            "completed_attempts": total,
            "completed_blocks": total // 4,
            "at_exact_2_1_1_boundary": total > 0 and total % 4 == 0,
        },
        "attempts": [
            _record_projection(
                _validate_record(
                    _resolve_evidence_path(attempt["record_path"], repository_root),
                    attempt,
                ),
                attempt["record_path"],
            )
            for attempt in validated["attempts"]
        ],
        "corrections": validated["corrections"],
        "restoration": validated["restoration"],
        "pull_request_url": validated["pull_request_url"],
        "evidence_isolation": {
            "accepted": "exact acts-seeding-v4-owned-static protocol revision 2 and canonical dataset only",
            "excluded": [
                "owned-static v4 pilot revision 1",
                "acts-seeding-v2",
                "acts-seeding-v3",
                "generated-input v4",
                "shared Athena dump",
            ],
        },
    }


def finalization_blockers(
    state: dict[str, Any], repository_root: Path = PROJECT_ROOT
) -> list[str]:
    blockers: list[str] = []
    control = state.get("control", {})
    scheduler = state.get("scheduler", {})
    if control.get("state") != "consumed":
        blockers.append("an authenticated stop request has not been consumed")
    if state.get("current_attempt") is not None:
        blockers.append("a candidate transaction remains active")
    attempts = state.get("attempts", [])
    counts = {
        category: sum(
            isinstance(attempt, dict) and attempt.get("classification") == category
            for attempt in attempts
        )
        for category in CATEGORIES
    }
    targets = scheduler.get("final_targets")
    if not isinstance(targets, dict) or any(
        counts[category] != targets.get(category) for category in CATEGORIES
    ):
        blockers.append(
            "exact final composition has not reached the persisted 2:1:1 target"
        )
    calibration = state.get("calibration")
    if (
        not isinstance(calibration, dict)
        or calibration.get("runs") != 5
        or calibration.get("valid") is not True
    ):
        blockers.append("five new valid Genesis calibration processes are not bound")
    restoration = state.get("restoration")
    if not isinstance(restoration, dict) or restoration.get("validated") is not True:
        blockers.append(
            "final private Genesis source/build/loaded closure restoration is not validated"
        )
    genesis = state.get("campaign", {}).get(
        "scientific_genesis_commit", SCIENTIFIC_GENESIS_COMMIT
    )
    process = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "diff",
            "--quiet",
            genesis,
            "--",
            "optimization-files",
        ],
        check=False,
    )
    if process.returncode != 0:
        blockers.append(
            "optimization-files/ is not restored exactly to scientific Genesis"
        )
    return blockers


def _read_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContinuousCampaignError(f"cannot read campaign state: {error}") from error
    return validate_state(value)


def _git_commit() -> str:
    process = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return process.stdout.strip()


def _issues_from_gh_axi() -> list[dict[str, Any]]:
    process = subprocess.run(
        [
            "gh-axi",
            "api",
            "repos/Aksth070600/autoresearch-acts-seeding/issues?state=all&labels=campaign-control&per_page=100&sort=created",
            "--jq",
            "[.[] | {number,title,body,html_url,"
            "labels:[.labels[] | {name}],user:{login:.user.login}}] | @base64",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode != 0:
        raise ContinuousCampaignError(
            f"authenticated GitHub issue read failed: {process.stderr.strip()}"
        )
    encoded = None
    truncated = None
    for line in process.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("body: "):
            encoded = stripped.removeprefix("body: ")
        elif stripped.startswith("truncated: "):
            truncated = stripped.removeprefix("truncated: ")
    if encoded is None or truncated != "false":
        raise ContinuousCampaignError(
            "authenticated GitHub issue response was missing or truncated"
        )
    try:
        value = json.loads(base64.b64decode(encoded, validate=True))
    except (ValueError, json.JSONDecodeError) as error:
        raise ContinuousCampaignError(
            "authenticated GitHub issue response is malformed"
        ) from error
    if not isinstance(value, list):
        raise ContinuousCampaignError(
            "authenticated GitHub issue response is malformed"
        )
    return value


def write_status(state: dict[str, Any], state_path: Path = DEFAULT_STATE) -> None:
    snapshot = build_status(state, _now(), _git_commit())
    atomic_write_json(DEFAULT_STATUS, snapshot)
    bridge = _bridge_live(state)
    validate_v3_live_state(bridge)
    atomic_write_json(DEFAULT_BRIDGE_INPUT, bridge)
    v3_snapshot = build_v3_status(bridge, [], _now(), _git_commit())
    atomic_write_json(DEFAULT_BRIDGE_STATUS, v3_snapshot)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("status", "check-stop", "consume-stop", "finalize")
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    state = _read_state(args.state)
    now = _now()
    should_write_status = True
    if args.command == "check-stop":
        state, changed = observe_stop(state, _issues_from_gh_axi(), now)
        if changed:
            atomic_write_json(args.state, state)
            print(
                f"observed authenticated stop: {state['control']['request']['issue_url']}"
            )
        else:
            should_write_status = False
            print("no new authenticated stop request")
    elif args.command == "consume-stop":
        state = consume_stop(state, now)
        atomic_write_json(args.state, state)
        print("consumed authenticated stop and fixed the current 2:1:1 block target")
    elif args.command == "finalize":
        blockers = finalization_blockers(state)
        if blockers:
            raise ContinuousCampaignError("; ".join(blockers))
        state = copy.deepcopy(state)
        state["control"]["state"] = "completed"
        state["control"]["completed_at"] = _iso(now)
        state["scheduler"]["state"] = "completed"
        atomic_write_json(args.state, state)
        print("static-v4 continuous campaign finalization passed")
    if should_write_status:
        write_status(state, args.state)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ContinuousCampaignError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {error}", file=os.sys.stderr)
        raise SystemExit(2)
