#!/usr/bin/env python3
"""Build exact immutable Development records for the four-slot static-v4 pilot."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from schema import (
    CANONICAL_PROJECT_GENESIS_COMMIT,
    CANONICAL_PROTOCOL_ID,
    PILOT_PROTOCOL_REVISION,
    ManifestError,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_dataset_directory,
)

CALIBRATION_SCHEMA = "acts-v4-owned-static-genesis-calibration-v2"
RECORD_SCHEMA = "acts-v4-owned-static-development-record-v2"


def _load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ManifestError(f"record input is not canonical JSON: {path}")
    return value


def _result(path: Path) -> dict[str, Any]:
    value = _load(path)
    if (
        value.get("schema") != "acts-seeding-v4-owned-static-result-v2"
        or value.get("protocol_revision") != PILOT_PROTOCOL_REVISION
        or value.get("qualification_only") is not False
        or value.get("protocol_id") != CANONICAL_PROTOCOL_ID
        or value.get("events") != 50
        or value.get("threads") != 1
        or value.get("process_exit_status") != 0
        or value.get("fpe", {}).get("observed_unmasked") != 0
        or value.get("static_process_gate", {}).get("passed") is not True
    ):
        raise ManifestError(f"invalid canonical scientific result: {path}")
    return value


def _fraction(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _identity_projection(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": result["dataset_id"],
        "input_event_hashes": result["input_event_hashes"],
        "stats": result["stats"],
        "manifest_sha256": result["identities"]["manifest_sha256"],
        "payload_sha256": result["identities"]["payload_sha256"],
        "dataset_source_manifest_sha256": result["identities"][
            "dataset_source_manifest_sha256"
        ],
        "dataset_build_manifest_sha256": result["identities"][
            "dataset_build_manifest_sha256"
        ],
        "overlay_manifest_sha256": result["identities"]["overlay_manifest_sha256"],
        "selected_particles": result["stats"]["nTotalParticles"],
        "matched_particles": result["stats"]["nTotalMatchedParticles"],
        "converted_tracks": result["stats"]["nTotalTracks"],
        "matched_tracks": result["stats"]["nTotalMatchedTracks"],
        "fake_tracks": result["stats"]["nTotalFakeTracks"],
        "duplicate_tracks": result["stats"]["nTotalDuplicateTracks"],
        "ordered_diagnostics_sha256": result["diagnostics"][
            "ordered_diagnostics_sha256"
        ],
    }


def calibrate(result_paths: list[Path]) -> dict[str, Any]:
    if len(result_paths) != 5:
        raise ManifestError("Genesis calibration requires exactly five results")
    results = [_result(path) for path in result_paths]
    if any(result["candidate_binding"] is not None for result in results):
        raise ManifestError("Genesis calibration cannot contain a candidate binding")
    baseline = _identity_projection(results[0])
    for result in results[1:]:
        if _identity_projection(result) != baseline:
            raise ManifestError("Genesis calibration identities or exact counts differ")
    timings = [result["timing"]["per_event_nanoseconds"] for result in results]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in timings
    ):
        raise ManifestError("Genesis timing is not finite and positive")
    median = sorted(timings)[2]
    deviation = max(abs(value - median) for value in timings)
    u = Fraction(deviation, median)
    if u >= 1:
        raise ManifestError("Genesis empirical noise envelope is at least one")
    interval = (Fraction(median) * (1 - u), Fraction(median) * (1 + u))
    calibration = {
        "schema": CALIBRATION_SCHEMA,
        "protocol_id": CANONICAL_PROTOCOL_ID,
        "protocol_revision": PILOT_PROTOCOL_REVISION,
        "dataset_id": baseline["dataset_id"],
        "genesis_commit": CANONICAL_PROJECT_GENESIS_COMMIT,
        "genesis_per_event_nanoseconds": timings,
        "median_per_event_nanoseconds": median,
        "relative_empirical_noise_envelope": _fraction(u),
        "empirical_noise_envelope_percent": _fraction(u * 100),
        "genesis_interval_nanoseconds": {
            "lower": _fraction(interval[0]),
            "upper": _fraction(interval[1]),
        },
        "baseline": baseline,
        "result_sha256": [sha256_file(path) for path in result_paths],
        "description": "empirical noise envelope, not a confidence level",
    }
    calibration["calibration_sha256"] = sha256_bytes(canonical_json_bytes(calibration))
    return calibration


def _as_fraction(value: dict[str, Any], field: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise ManifestError(f"{field} is not an exact fraction")
    numerator, denominator = value["numerator"], value["denominator"]
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or denominator <= 0
    ):
        raise ManifestError(f"{field} is malformed")
    return Fraction(numerator, denominator)


def classify_candidate(
    result: dict[str, Any], calibration: dict[str, Any]
) -> dict[str, Any]:
    if (
        calibration.get("schema") != CALIBRATION_SCHEMA
        or calibration.get("protocol_revision") != PILOT_PROTOCOL_REVISION
    ):
        raise ManifestError("Genesis calibration schema mismatch")
    if result["dataset_id"] != calibration["dataset_id"]:
        raise ManifestError("candidate dataset differs from Genesis")
    baseline = calibration["baseline"]
    if result["input_event_hashes"] != baseline["input_event_hashes"]:
        raise ManifestError("candidate event hashes differ from Genesis")
    stats = result["stats"]
    if stats["nTotalParticles"] != baseline["selected_particles"]:
        raise ManifestError("candidate truth denominator differs from Genesis")
    candidate_ns = result["timing"]["per_event_nanoseconds"]
    if (
        not isinstance(candidate_ns, int)
        or isinstance(candidate_ns, bool)
        or candidate_ns <= 0
    ):
        raise ManifestError("candidate timing is invalid")
    genesis_ns = calibration["median_per_event_nanoseconds"]
    u = _as_fraction(
        calibration["relative_empirical_noise_envelope"], "Genesis envelope"
    )
    candidate_interval = (
        Fraction(candidate_ns) * (1 - u),
        Fraction(candidate_ns) * (1 + u),
    )
    genesis_interval = (
        Fraction(genesis_ns) * (1 - u),
        Fraction(genesis_ns) * (1 + u),
    )
    if candidate_interval[1] < genesis_interval[0]:
        timing_label = "confidently faster"
    elif candidate_interval[0] > genesis_interval[1]:
        timing_label = "confidently slower"
    elif candidate_ns == genesis_ns:
        timing_label = "equality, inconclusive"
    elif (
        candidate_interval[1] == genesis_interval[0]
        or candidate_interval[0] == genesis_interval[1]
    ):
        timing_label = "boundary, inconclusive"
    elif candidate_ns < genesis_ns:
        timing_label = "directional faster, inconclusive"
    elif candidate_ns > genesis_ns:
        timing_label = "directional slower, inconclusive"
    else:
        timing_label = "inconclusive"

    candidate_efficiency = Fraction(
        stats["nTotalMatchedParticles"], stats["nTotalParticles"]
    )
    genesis_efficiency = Fraction(
        baseline["matched_particles"], baseline["selected_particles"]
    )
    if candidate_efficiency > genesis_efficiency:
        efficiency_label = "gain"
    elif candidate_efficiency < genesis_efficiency:
        efficiency_label = "regression"
    else:
        efficiency_label = "equal"

    timing_fast = timing_label == "confidently faster"
    timing_slow = timing_label == "confidently slower"
    if timing_fast and efficiency_label in {"gain", "equal"}:
        overall = "valid improvement"
    elif efficiency_label == "gain" and not timing_slow:
        overall = "valid improvement"
    elif (timing_fast and efficiency_label == "regression") or (
        timing_slow and efficiency_label == "gain"
    ):
        overall = "mixed"
    elif timing_slow or efficiency_label == "regression":
        overall = "regression"
    else:
        overall = "inconclusive"
    return {
        "timing": {
            "label": timing_label,
            "candidate_per_event_nanoseconds": candidate_ns,
            "genesis_median_per_event_nanoseconds": genesis_ns,
            "candidate_interval_nanoseconds": {
                "lower": _fraction(candidate_interval[0]),
                "upper": _fraction(candidate_interval[1]),
            },
            "genesis_interval_nanoseconds": {
                "lower": _fraction(genesis_interval[0]),
                "upper": _fraction(genesis_interval[1]),
            },
            "empirical_noise_envelope": _fraction(u),
        },
        "efficiency": {
            "label": efficiency_label,
            "candidate": _fraction(candidate_efficiency),
            "genesis": _fraction(genesis_efficiency),
        },
        "overall": overall,
        "timing_regression": timing_slow,
        "efficiency_regression": efficiency_label == "regression",
    }


def _seconds(value: str, field: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ManifestError(f"{field} is malformed") from error
    if not parsed.is_finite() or parsed < 0:
        raise ManifestError(f"{field} is invalid")
    return parsed


def build_record(
    result_path: Path,
    dataset_path: Path,
    candidate: str,
    slot: int | None,
    implementation_commit: str,
    proposal_path: Path | None,
    calibration_path: Path | None,
    preparation_seconds: str,
    build_seconds: str,
    record_preparation_seconds: str,
    total_latency_seconds: str,
    correction_path: Path | None,
) -> dict[str, Any]:
    result = _result(result_path)
    manifest, detached = validate_dataset_directory(
        dataset_path,
        expected_protocol_id=CANONICAL_PROTOCOL_ID,
        expected_dataset_id=result["dataset_id"],
        expected_events=50,
    )
    truth_hashes = [
        event["section_sha256"]["selected_particles"]
        for event in manifest["dataset"]["events"]
    ]
    proposal = _load(proposal_path) if proposal_path is not None else None
    if candidate == "Genesis":
        if (
            slot is not None
            or proposal is not None
            or result["candidate_binding"] is not None
        ):
            raise ManifestError("Genesis record contains candidate metadata")
        classification = None
        category = "baseline"
        mechanism_key = "canonical-genesis"
        proposal_hash = None
    else:
        if (
            isinstance(slot, bool)
            or not isinstance(slot, int)
            or slot < 1
            or proposal is None
            or calibration_path is None
        ):
            raise ManifestError(
                "candidate record lacks a positive slot, proposal, or calibration"
            )
        proposal_hash = sha256_bytes(canonical_json_bytes(proposal))
        if (
            proposal.get("candidate") != candidate
            or proposal.get("implementation_commit") != implementation_commit
        ):
            raise ManifestError("record proposal binding mismatch")
        if (
            result["candidate_binding"] is None
            or result["candidate_binding"]["proposal_sha256"] != proposal_hash
        ):
            raise ManifestError("scientific process loaded a different proposal")
        calibration = _load(calibration_path)
        classification = classify_candidate(result, calibration)
        category = proposal["classification"]
        mechanism_key = proposal["mechanism_key"]

    preparation = _seconds(preparation_seconds, "preparation duration")
    build = _seconds(build_seconds, "build duration")
    record_preparation = _seconds(record_preparation_seconds, "record duration")
    total = _seconds(total_latency_seconds, "total latency")
    corrections = (
        [] if correction_path is None else _load(correction_path).get("corrections")
    )
    if not isinstance(corrections, list):
        raise ManifestError("correction evidence is malformed")
    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "protocol_id": CANONICAL_PROTOCOL_ID,
        "protocol_revision": PILOT_PROTOCOL_REVISION,
        "dataset_id": result["dataset_id"],
        "category": "Development",
        "status": "passed",
        "candidate_name": candidate,
        "baseline": candidate == "Genesis",
        "slot": slot,
        "classification": category,
        "mechanism_key": mechanism_key,
        "implementation_commit": implementation_commit,
        "proposal": proposal,
        "proposal_sha256": proposal_hash,
        "scientific_processes": 1,
        "result": result,
        "scientific_classification": classification,
        "truth_denominator_hashes": truth_hashes,
        "dataset_identity": {
            "publication_path": str(dataset_path.resolve(strict=True)),
            "manifest_sha256": detached["manifest.json"],
            "manifest_identity_sha256": result["dataset_id"].rsplit("-", 1)[1],
            "payload_sha256": detached["payload.root"],
            "overlay_manifest_sha256": manifest["identities"][
                "overlay_manifest_sha256"
            ],
            "production_source_manifest_sha256": manifest["identities"][
                "source_manifest_sha256"
            ],
            "production_build_manifest_sha256": manifest["identities"][
                "build_manifest_sha256"
            ],
            "geometry_tgeo_sha256": manifest["identities"]["geometry_tgeo_sha256"],
            "geometry_material_sha256": manifest["identities"][
                "geometry_material_sha256"
            ],
            "field_sha256": manifest["identities"]["field_sha256"],
            "digitization_sha256": manifest["identities"]["digitization_sha256"],
            "pixel_geometry_selection_sha256": manifest["identities"][
                "pixel_geometry_selection_sha256"
            ],
            "seeding_config_sha256": manifest["identities"]["seeding_config_sha256"],
            "builder_sha256": manifest["identities"]["builder_sha256"],
            "project_genesis_commit": manifest["production"]["project_genesis_commit"],
            "production": manifest["production"],
        },
        "latency": {
            "preparation_seconds": str(preparation),
            "build_seconds": str(build),
            "record_preparation_seconds": str(record_preparation),
            "queue_to_immutable_record_seconds": str(total),
            "preparation_build_target_seconds": 45,
            "preparation_build_target_passed": preparation <= 45,
            "static_process_target_seconds": 180,
            "static_process_target_passed": result["static_process_gate"]["passed"],
            "queue_to_record_target_seconds": 300,
            "queue_to_record_target_passed": total <= 300,
        },
        "corrections": corrections,
        "generalization_scope": "fixed canonical 50-event dataset only; no claim for other event populations",
    }
    if total > 300:
        record["status"] = "invalid"
        record["scientific_classification"] = None
    record["record_sha256"] = sha256_bytes(canonical_json_bytes(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    calibration = subparsers.add_parser("calibrate")
    calibration.add_argument("--result", type=Path, action="append", required=True)
    calibration.add_argument("--output", type=Path, required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--result", type=Path, required=True)
    record.add_argument("--dataset", type=Path, required=True)
    record.add_argument("--candidate", required=True)
    record.add_argument("--slot", type=int)
    record.add_argument("--implementation-commit", required=True)
    record.add_argument("--proposal", type=Path)
    record.add_argument("--calibration", type=Path)
    record.add_argument("--preparation-seconds", required=True)
    record.add_argument("--build-seconds", required=True)
    record.add_argument("--record-preparation-seconds", required=True)
    record.add_argument("--total-latency-seconds", required=True)
    record.add_argument("--corrections", type=Path)
    record.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ManifestError("refusing to replace campaign evidence")
    if args.command == "calibrate":
        value = calibrate(args.result)
    else:
        value = build_record(
            args.result,
            args.dataset,
            args.candidate,
            args.slot,
            args.implementation_commit,
            args.proposal,
            args.calibration,
            args.preparation_seconds,
            args.build_seconds,
            args.record_preparation_seconds,
            args.total_latency_seconds,
            args.corrections,
        )
    atomic_write_json(args.output, value)
    print(f"wrote={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
