"""Candidate proposal validation and deterministic pre-run binding."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

PROPOSAL_SCHEMA_VERSION = "1.0.0"
PRIMARY_PREDICTIONS = frozenset(
    {
        "timed_seeding_time_per_event_ms",
        "timed_seeding_particle_efficiency",
    }
)
PREDICTED_DIRECTIONS = frozenset({"decrease", "unchanged", "increase"})
SOURCE_TYPES = frozenset(
    {
        "Genesis",
        "prior record/commit",
        "inspected source code",
        "external primary source",
    }
)
GROUNDING_SOURCE_TYPES = frozenset(
    {"inspected source code", "external primary source"}
)
FULL_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
CANDIDATE_NAME = re.compile(r"[A-Za-z0-9._-]+")
INTENDED_FILE = re.compile(r"optimization-files/[^#\x00-\x1f]+")
HISTORICAL_RECORD = re.compile(
    r"records/(?:Development|Evaluation)/[^/\x00-\x1f]+/summary\.json"
)
FILE_LINE_RANGE = re.compile(
    r"optimization-files/[^#,\x00-\x1f]+#L[1-9][0-9]*-L[1-9][0-9]*"
    r"(?:,L[1-9][0-9]*-L[1-9][0-9]*)*"
)


class ProposalError(ValueError):
    """Raised when a candidate proposal or its measured copy is invalid."""


def _keys(value: dict[str, Any], field: str, allowed: set[str], required: set[str]) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise ProposalError(f"{field} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ProposalError(f"{field} has unsupported fields: {', '.join(sorted(unknown))}")


def _text(value: Any, field: str, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ProposalError(
            f"{field} must be a non-empty string of at most {maximum} characters"
        )
    normalized = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ProposalError(f"{field} contains a control character")
    return normalized


def _commit(value: Any, field: str) -> str:
    if not isinstance(value, str) or not FULL_COMMIT_SHA.fullmatch(value.lower()):
        raise ProposalError(f"{field} must be a full Git SHA")
    return value.lower()


def normalize_combination_provenance(value: Any, field: str) -> dict[str, Any]:
    """Validate provenance syntax. Campaign validation also checks source lineage."""

    if not isinstance(value, dict):
        raise ProposalError(f"{field} must be an object")
    fields = {"sources", "compatibility_rationale", "interaction_hypothesis"}
    _keys(value, field, fields, fields)
    sources = value["sources"]
    if not isinstance(sources, list) or len(sources) < 2:
        raise ProposalError(f"{field}.sources must contain at least two sources")
    normalized_sources: list[dict[str, Any]] = []
    candidates: set[str] = set()
    source_fields = {
        "candidate",
        "mechanism_key",
        "implementation_commit",
        "directly_inspected",
    }
    historical_fields = {"historical_record", "files_changed"}
    for index, source in enumerate(sources):
        source_field = f"{field}.sources[{index}]"
        if not isinstance(source, dict):
            raise ProposalError(f"{source_field} must be an object")
        present_historical_fields = set(source) & historical_fields
        if present_historical_fields and present_historical_fields != historical_fields:
            raise ProposalError(
                f"{source_field} must provide historical_record and files_changed together"
            )
        _keys(
            source,
            source_field,
            source_fields | historical_fields,
            source_fields | present_historical_fields,
        )
        candidate = _text(source["candidate"], f"{source_field}.candidate", 80)
        if not CANDIDATE_NAME.fullmatch(candidate):
            raise ProposalError(f"{source_field}.candidate has unsupported characters")
        if candidate in candidates:
            raise ProposalError(f"{field}.sources must name distinct candidates")
        candidates.add(candidate)
        if source["directly_inspected"] is not True:
            raise ProposalError(f"{source_field}.directly_inspected must be true")
        normalized_source: dict[str, Any] = {
            "candidate": candidate,
            "mechanism_key": _text(
                source["mechanism_key"], f"{source_field}.mechanism_key", 120
            ),
            "implementation_commit": _commit(
                source["implementation_commit"],
                f"{source_field}.implementation_commit",
            ),
            "directly_inspected": True,
        }
        if present_historical_fields:
            record = _text(
                source["historical_record"],
                f"{source_field}.historical_record",
                500,
            )
            if not HISTORICAL_RECORD.fullmatch(record):
                raise ProposalError(
                    f"{source_field}.historical_record must name an exact summary path"
                )
            files = source["files_changed"]
            if not isinstance(files, list) or not files:
                raise ProposalError(
                    f"{source_field}.files_changed must be a non-empty array"
                )
            normalized_files = [
                _text(item, f"{source_field}.files_changed[{index}]", 300)
                for index, item in enumerate(files)
            ]
            if any(not FILE_LINE_RANGE.fullmatch(item) for item in normalized_files):
                raise ProposalError(
                    f"{source_field}.files_changed must contain exact optimization file ranges"
                )
            if len(set(normalized_files)) != len(normalized_files):
                raise ProposalError(f"{source_field}.files_changed must be unique")
            normalized_source.update(
                {"historical_record": record, "files_changed": normalized_files}
            )
        normalized_sources.append(normalized_source)
    return {
        "sources": normalized_sources,
        "compatibility_rationale": _text(
            value["compatibility_rationale"], f"{field}.compatibility_rationale", 500
        ),
        "interaction_hypothesis": _text(
            value["interaction_hypothesis"], f"{field}.interaction_hypothesis", 500
        ),
    }


def normalize_source_reference(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProposalError(f"{field} must be an object")
    required = {"source_type", "reference", "relevance", "directly_inspected"}
    allowed = required | {"inspected_scope", "acts_mapping"}
    _keys(value, field, allowed, required)
    source_type = value["source_type"]
    if source_type not in SOURCE_TYPES:
        raise ProposalError(f"{field}.source_type is invalid")
    directly_inspected = value["directly_inspected"]
    if not isinstance(directly_inspected, bool):
        raise ProposalError(f"{field}.directly_inspected must be a boolean")
    reference = _text(value["reference"], f"{field}.reference", 500)
    normalized: dict[str, Any] = {
        "source_type": source_type,
        "reference": reference,
        "relevance": _text(value["relevance"], f"{field}.relevance", 500),
        "directly_inspected": directly_inspected,
    }
    if source_type in GROUNDING_SOURCE_TYPES:
        if not directly_inspected:
            raise ProposalError(f"{field} must be directly inspected")
        if not reference.startswith("https://") or any(
            moving in reference.lower() for moving in ("/main/", "/master/", "/latest/")
        ):
            raise ProposalError(f"{field}.reference must be a permanent HTTPS locator")
        for name in ("inspected_scope", "acts_mapping"):
            if name not in value:
                raise ProposalError(f"{field}.{name} is required for a primary source")
            normalized[name] = _text(value[name], f"{field}.{name}", 700)
    else:
        for name in ("inspected_scope", "acts_mapping"):
            if name in value:
                normalized[name] = _text(value[name], f"{field}.{name}", 700)
    return normalized


def normalize_proposal(value: Any, field: str = "proposal") -> dict[str, Any]:
    """Return the deterministic, schema-normalized proposal representation."""

    if not isinstance(value, dict):
        raise ProposalError(f"{field} must be an object")
    required = {
        "schema_version",
        "candidate",
        "implementation_commit",
        "hypothesis",
        "falsifier",
        "predicted_directions",
        "expected_hot_path",
        "changed_symbols",
        "intended_files",
        "novelty_reason",
        "source_references",
        "combination_provenance",
    }
    _keys(value, field, required, required)
    if value["schema_version"] != PROPOSAL_SCHEMA_VERSION:
        raise ProposalError(
            f"{field}.schema_version must be {PROPOSAL_SCHEMA_VERSION}"
        )
    candidate = _text(value["candidate"], f"{field}.candidate", 80)
    if candidate == "Genesis" or not CANDIDATE_NAME.fullmatch(candidate):
        raise ProposalError(f"{field}.candidate must be a non-Genesis candidate name")

    predictions = value["predicted_directions"]
    if not isinstance(predictions, dict) or set(predictions) != PRIMARY_PREDICTIONS:
        raise ProposalError(
            f"{field}.predicted_directions must name both primary objectives exactly"
        )
    normalized_predictions: dict[str, str] = {}
    for objective in sorted(PRIMARY_PREDICTIONS):
        direction = predictions[objective]
        if direction not in PREDICTED_DIRECTIONS:
            raise ProposalError(
                f"{field}.predicted_directions.{objective} has an invalid direction"
            )
        normalized_predictions[objective] = direction

    symbols = value["changed_symbols"]
    if not isinstance(symbols, list) or not symbols:
        raise ProposalError(f"{field}.changed_symbols must be a non-empty array")
    normalized_symbols = [
        _text(symbol, f"{field}.changed_symbols[{index}]", 200)
        for index, symbol in enumerate(symbols)
    ]
    if len(set(normalized_symbols)) != len(normalized_symbols):
        raise ProposalError(f"{field}.changed_symbols must be unique")

    intended_files = value["intended_files"]
    if not isinstance(intended_files, list) or not intended_files:
        raise ProposalError(f"{field}.intended_files must be a non-empty array")
    normalized_files = []
    for index, intended_file in enumerate(intended_files):
        intended_file = _text(
            intended_file, f"{field}.intended_files[{index}]", 300
        )
        if not INTENDED_FILE.fullmatch(intended_file):
            raise ProposalError(
                f"{field}.intended_files[{index}] must be an exact optimization-files path"
            )
        normalized_files.append(intended_file)
    if len(set(normalized_files)) != len(normalized_files):
        raise ProposalError(f"{field}.intended_files must be unique")

    references = value["source_references"]
    if not isinstance(references, list) or not references:
        raise ProposalError(f"{field}.source_references must be a non-empty array")
    normalized_references = [
        normalize_source_reference(reference, f"{field}.source_references[{index}]")
        for index, reference in enumerate(references)
    ]
    provenance = value["combination_provenance"]
    normalized_provenance = (
        None
        if provenance is None
        else normalize_combination_provenance(
            provenance, f"{field}.combination_provenance"
        )
    )
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "candidate": candidate,
        "implementation_commit": _commit(
            value["implementation_commit"], f"{field}.implementation_commit"
        ),
        "hypothesis": _text(value["hypothesis"], f"{field}.hypothesis", 1000),
        "falsifier": _text(value["falsifier"], f"{field}.falsifier", 1000),
        "predicted_directions": normalized_predictions,
        "expected_hot_path": _text(
            value["expected_hot_path"], f"{field}.expected_hot_path", 700
        ),
        "changed_symbols": normalized_symbols,
        "intended_files": normalized_files,
        "novelty_reason": _text(
            value["novelty_reason"], f"{field}.novelty_reason", 700
        ),
        "source_references": normalized_references,
        "combination_provenance": normalized_provenance,
    }


def proposal_hash(proposal: dict[str, Any], implementation_commit: str) -> str:
    """Hash canonical normalized proposal JSON together with the implementation commit."""

    normalized = normalize_proposal(proposal)
    commit = _commit(implementation_commit, "implementation_commit")
    payload = json.dumps(
        {"implementation_commit": commit, "proposal": normalized},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def bind_proposal(
    proposal: Any,
    candidate: str,
    implementation_commit: str,
    implementation_files: list[str] | None = None,
) -> dict[str, Any]:
    """Bind a normalized proposal to the candidate implementation before a run."""

    normalized = normalize_proposal(proposal)
    commit = _commit(implementation_commit, "implementation_commit")
    if normalized["candidate"] != candidate:
        raise ProposalError("proposal candidate does not match the evaluated candidate")
    if normalized["implementation_commit"] != commit:
        raise ProposalError("proposal implementation commit does not match the candidate")
    if implementation_files is not None and sorted(normalized["intended_files"]) != sorted(
        implementation_files
    ):
        raise ProposalError(
            "proposal intended_files do not match files changed by the implementation commit"
        )
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "proposal": normalized,
        "proposal_hash": proposal_hash(normalized, commit),
    }


def proposal_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Validate and return a measured proposal copy, or None for historical evidence."""

    binding = summary.get("proposal_binding")
    if binding is None:
        return None
    if not isinstance(binding, dict) or set(binding) != {
        "schema_version",
        "proposal",
        "proposal_hash",
    }:
        raise ProposalError("summary proposal_binding fields are invalid")
    if binding["schema_version"] != PROPOSAL_SCHEMA_VERSION:
        raise ProposalError("summary proposal_binding schema version is invalid")
    proposal = normalize_proposal(binding["proposal"], "summary.proposal_binding.proposal")
    candidate = summary.get("candidate_name")
    commit = summary.get("implementation_commit")
    expected = bind_proposal(proposal, candidate, commit)
    if binding["proposal_hash"] != expected["proposal_hash"]:
        raise ProposalError("summary proposal hash does not match its measured proposal copy")
    if summary.get("combination_provenance") != proposal["combination_provenance"]:
        raise ProposalError(
            "summary combination provenance does not match its measured proposal copy"
        )
    return proposal


def has_primary_source_grounding(proposal: dict[str, Any]) -> bool:
    normalized = normalize_proposal(proposal)
    return any(
        reference["source_type"] in GROUNDING_SOURCE_TYPES
        for reference in normalized["source_references"]
    )


def median_absolute_deviation(values: list[float]) -> float:
    """Return the unscaled median absolute deviation."""

    if not values or any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("MAD requires finite numeric values")
    ordered = sorted(float(value) for value in values)
    size = len(ordered)
    center = ordered[size // 2] if size % 2 else (ordered[size // 2 - 1] + ordered[size // 2]) / 2
    deviations = sorted(abs(value - center) for value in ordered)
    return deviations[size // 2] if size % 2 else (deviations[size // 2 - 1] + deviations[size // 2]) / 2
