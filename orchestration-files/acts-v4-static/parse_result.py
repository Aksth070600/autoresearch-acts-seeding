#!/usr/bin/env python3
"""Build one strict, atomic static-v4 qualification result."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from schema import (
    ACTS_COMMIT,
    ACTS_TAG,
    PROVISIONAL_PROTOCOL_PREFIX,
    ManifestError,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
)

STATS = (
    "nTotalTracks",
    "nTotalMatchedTracks",
    "nTotalFakeTracks",
    "nTotalDuplicateTracks",
    "nTotalParticles",
    "nTotalMatchedParticles",
    "nTotalDuplicateParticles",
    "nTotalFakeParticles",
)
RAW_KEYS = {
    "protocol_id",
    "dataset_id",
    "event_count",
    "thread_count",
    "completed_event_ids",
    "input_event_hashes",
    "stats",
    "diagnostics",
    "identities",
    "expected_unmasked_fpes",
    "root_plots",
}
DIAGNOSTIC_KEYS = {
    "raw_seed_count",
    "estimated_seed_count",
    "estimated_parameter_count",
    "converted_track_count",
    "matcher_classification_counts",
    "ordered_diagnostics_sha256",
}
IDENTITY_KEYS = {
    "acts_tag",
    "acts_commit",
    "manifest_sha256",
    "payload_sha256",
    "source_manifest_sha256",
    "build_manifest_sha256",
    "overlay_manifest_sha256",
    "runner_sha256",
}


def _exact_object(value: Any, keys: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ManifestError(f"{path} has unexpected keys")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManifestError(f"{path} must be a nonnegative integer")
    return value


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ManifestError(f"{path} must be a lowercase SHA-256")
    return value


def parse_timing_csv(text: str, event_count: int) -> dict[str, Any]:
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except csv.Error as error:
        raise ManifestError(f"timing CSV is malformed: {error}") from error
    expected_fields = ["identifier", "time_total_s", "time_perevent_s"]
    if not rows or list(rows[0]) != expected_fields:
        raise ManifestError("timing CSV header mismatch")
    matches = [row for row in rows if row["identifier"] == "Algorithm:GridTripletSeedingAlgorithm"]
    if len(matches) != 1:
        raise ManifestError("timing CSV must contain one GridTripletSeedingAlgorithm row")
    row = matches[0]
    try:
        total = Decimal(row["time_total_s"])
        per_event = Decimal(row["time_perevent_s"])
    except (InvalidOperation, TypeError) as error:
        raise ManifestError("seeding timing is not decimal") from error
    if not total.is_finite() or not per_event.is_finite() or total <= 0 or per_event <= 0:
        raise ManifestError("seeding timing must be finite and positive")
    # Sequencer writes each decimal independently with stream precision, so
    # total/events can differ from the printed per-event value by their last
    # displayed places. Bound the check by exactly those decimal quanta.
    total_quantum = Decimal(1).scaleb(total.as_tuple().exponent)
    per_event_quantum = Decimal(1).scaleb(per_event.as_tuple().exponent)
    tolerance = total_quantum / event_count + per_event_quantum
    if abs(total / event_count - per_event) > tolerance:
        raise ManifestError("seeding total and per-event timing are inconsistent")
    total_ns = total * Decimal(1_000_000_000)
    per_event_ns = per_event * Decimal(1_000_000_000)
    if total_ns != total_ns.to_integral_value() or per_event_ns != per_event_ns.to_integral_value():
        raise ManifestError("timing CSV precision is finer than one nanosecond")
    return {
        "algorithm": "GridTripletSeedingAlgorithm",
        "total_seconds": str(total),
        "per_event_seconds": str(per_event),
        "total_nanoseconds": int(total_ns),
        "per_event_nanoseconds": int(per_event_ns),
    }


def _elapsed_seconds(value: str) -> Decimal:
    parts = value.split(":")
    try:
        numbers = [Decimal(part) for part in parts]
    except InvalidOperation as error:
        raise ManifestError("GNU time elapsed value is malformed") from error
    if len(numbers) == 2:
        minutes, seconds = numbers
        result = minutes * 60 + seconds
    elif len(numbers) == 3:
        hours, minutes, seconds = numbers
        result = hours * 3600 + minutes * 60 + seconds
    else:
        raise ManifestError("GNU time elapsed value has an unsupported shape")
    if not result.is_finite() or result < 0:
        raise ManifestError("GNU time elapsed value is invalid")
    return result


def parse_time_v(text: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        for label, key in (
            ("User time (seconds):", "user_seconds"),
            ("System time (seconds):", "system_seconds"),
            ("Elapsed (wall clock) time (h:mm:ss or m:ss):", "elapsed"),
            ("Maximum resident set size (kbytes):", "peak_rss_kb"),
            ("Exit status:", "time_exit_status"),
        ):
            if line.startswith(label):
                if key in fields:
                    raise ManifestError(f"GNU time contains duplicate {key}")
                fields[key] = line[len(label) :].strip()
    required = {"user_seconds", "system_seconds", "elapsed", "peak_rss_kb", "time_exit_status"}
    if set(fields) != required:
        raise ManifestError(f"GNU time fields differ: {sorted(set(fields) ^ required)}")
    try:
        user = Decimal(fields["user_seconds"])
        system = Decimal(fields["system_seconds"])
    except InvalidOperation as error:
        raise ManifestError("GNU time CPU values are malformed") from error
    if not user.is_finite() or not system.is_finite() or user < 0 or system < 0:
        raise ManifestError("GNU time CPU values are invalid")
    elapsed = _elapsed_seconds(fields["elapsed"])
    peak = _nonnegative_int(int(fields["peak_rss_kb"]), "peak RSS")
    status = _nonnegative_int(int(fields["time_exit_status"]), "GNU time exit status")
    return {
        "wall_seconds": str(elapsed),
        "user_seconds": str(user),
        "system_seconds": str(system),
        "peak_rss_kb": peak,
        "time_exit_status": status,
    }


def parse_completion_and_fpe(log: str) -> tuple[int, int]:
    completed = re.findall(r"Processed (\d+) events in", log)
    if len(completed) != 1:
        raise ManifestError("process log must contain one event-completion summary")
    encountered = re.findall(r"Encountered (\d+) unmasked FPEs", log)
    none = re.findall(r"No unmasked FPEs encountered", log)
    if len(encountered) + len(none) != 1:
        raise ManifestError("process log must contain one unmasked-FPE summary")
    fpes = int(encountered[0]) if encountered else 0
    return int(completed[0]), fpes


def _rate(numerator: int, denominator: int) -> dict[str, int]:
    return {"numerator": numerator, "denominator": denominator}


def build_result(
    raw: Any,
    *,
    timing_csv: str,
    time_v: str,
    process_log: str,
    process_exit_status: int,
    total_latency_seconds: str | None = None,
) -> dict[str, Any]:
    raw = _exact_object(raw, RAW_KEYS, "raw result")
    protocol_id = raw["protocol_id"]
    if not isinstance(protocol_id, str) or (
        protocol_id != PROVISIONAL_PROTOCOL_PREFIX
        and not protocol_id.startswith(PROVISIONAL_PROTOCOL_PREFIX + "-")
    ):
        raise ManifestError("result protocol is outside the static-v4 qualification namespace")
    if not isinstance(raw["dataset_id"], str) or not raw["dataset_id"]:
        raise ManifestError("result dataset ID is missing")
    events = _nonnegative_int(raw["event_count"], "event_count")
    if events < 1 or raw["thread_count"] != 1:
        raise ManifestError("result event/thread contract mismatch")
    expected_ids = list(range(events))
    if raw["completed_event_ids"] != expected_ids:
        raise ManifestError("reader did not complete every ordered event")
    hashes = raw["input_event_hashes"]
    if not isinstance(hashes, list) or len(hashes) != events:
        raise ManifestError("input event hash count mismatch")
    for index, value in enumerate(hashes):
        _sha(value, f"input_event_hashes[{index}]")

    stats = _exact_object(raw["stats"], set(STATS), "stats")
    exact_stats = {key: _nonnegative_int(stats[key], f"stats.{key}") for key in STATS}
    if exact_stats["nTotalTracks"] == 0 or exact_stats["nTotalParticles"] == 0:
        raise ManifestError("exact rate denominators must be positive")
    for count, total in (
        ("nTotalMatchedTracks", "nTotalTracks"),
        ("nTotalFakeTracks", "nTotalTracks"),
        ("nTotalDuplicateTracks", "nTotalTracks"),
        ("nTotalMatchedParticles", "nTotalParticles"),
        ("nTotalDuplicateParticles", "nTotalParticles"),
        ("nTotalFakeParticles", "nTotalParticles"),
    ):
        if exact_stats[count] > exact_stats[total]:
            raise ManifestError(f"stats.{count} exceeds stats.{total}")
    diagnostics = _exact_object(raw["diagnostics"], DIAGNOSTIC_KEYS, "diagnostics")
    exact_diagnostics: dict[str, Any] = {
        key: _nonnegative_int(diagnostics[key], f"diagnostics.{key}")
        for key in (
            "raw_seed_count",
            "estimated_seed_count",
            "estimated_parameter_count",
            "converted_track_count",
        )
    }
    classifications = _exact_object(
        diagnostics["matcher_classification_counts"],
        {"matched", "fake", "duplicate", "unknown"},
        "matcher classifications",
    )
    exact_diagnostics["matcher_classification_counts"] = {
        key: _nonnegative_int(value, f"matcher classifications.{key}")
        for key, value in classifications.items()
    }
    exact_diagnostics["ordered_diagnostics_sha256"] = _sha(
        diagnostics["ordered_diagnostics_sha256"], "ordered diagnostics hash"
    )
    if exact_diagnostics["converted_track_count"] != exact_stats["nTotalTracks"]:
        raise ManifestError("converted-track count differs from collector total tracks")
    if exact_diagnostics["estimated_parameter_count"] != exact_diagnostics["estimated_seed_count"]:
        raise ManifestError("estimated parameter and filtered seed counts differ")
    classification_counts = exact_diagnostics["matcher_classification_counts"]
    if sum(classification_counts.values()) != exact_stats["nTotalTracks"]:
        raise ManifestError("matcher classification multiplicity differs from tracks")
    if (
        classification_counts["matched"] + classification_counts["duplicate"]
        != exact_stats["nTotalMatchedTracks"]
        or classification_counts["fake"] != exact_stats["nTotalFakeTracks"]
        or classification_counts["duplicate"]
        != exact_stats["nTotalDuplicateTracks"]
    ):
        raise ManifestError("matcher classifications differ from exact collector stats")

    identities = _exact_object(raw["identities"], IDENTITY_KEYS, "identities")
    exact_identities = dict(identities)
    if identities["acts_tag"] != ACTS_TAG or identities["acts_commit"] != ACTS_COMMIT:
        raise ManifestError("result ACTS identity mismatch")
    for key in IDENTITY_KEYS - {"acts_tag", "acts_commit"}:
        _sha(identities[key], f"identities.{key}")

    if raw["expected_unmasked_fpes"] != 0:
        raise ManifestError("static qualification expected-FPE policy drifted")
    if type(raw["root_plots"]) is not bool or raw["root_plots"]:
        raise ManifestError("ordinary qualification must keep ROOT plots off")
    if isinstance(process_exit_status, bool) or not isinstance(process_exit_status, int):
        raise ManifestError("process exit status is malformed")

    completed_count, fpes = parse_completion_and_fpe(process_log)
    resources = parse_time_v(time_v)
    if completed_count != events:
        raise ManifestError("sequencer completion count mismatch")
    if fpes != 0:
        raise ManifestError(f"unexpected static-process FPE count: {fpes}")
    if process_exit_status != 0 or resources["time_exit_status"] != process_exit_status:
        raise ManifestError("static process did not exit successfully")

    timing = parse_timing_csv(timing_csv, events)
    wall = Decimal(resources["wall_seconds"])
    if wall > Decimal(180):
        raise ManifestError(f"static process exceeded 180-second target: {wall}")
    total_gate: dict[str, Any] | None = None
    if total_latency_seconds is not None:
        try:
            total = Decimal(total_latency_seconds)
        except InvalidOperation as error:
            raise ManifestError("total latency is malformed") from error
        if not total.is_finite() or total < 0:
            raise ManifestError("total latency is invalid")
        if total > Decimal(300):
            raise ManifestError(f"total latency exceeded 300-second target: {total}")
        total_gate = {"seconds": str(total), "target_seconds": 300, "passed": True}

    result: dict[str, Any] = {
        "schema": "acts-seeding-v4-owned-static-result-v1",
        "qualification_only": True,
        "protocol_id": protocol_id,
        "dataset_id": raw["dataset_id"],
        "events": events,
        "threads": 1,
        "completed_event_ids": expected_ids,
        "input_event_hashes": hashes,
        "stats": exact_stats,
        "rates": {
            "particle_efficiency": _rate(
                exact_stats["nTotalMatchedParticles"], exact_stats["nTotalParticles"]
            ),
            "fake_tracks": _rate(exact_stats["nTotalFakeTracks"], exact_stats["nTotalTracks"]),
            "duplicate_tracks": _rate(
                exact_stats["nTotalDuplicateTracks"], exact_stats["nTotalTracks"]
            ),
        },
        "diagnostics": exact_diagnostics,
        "timing": timing,
        "resources": resources,
        "fpe": {"expected_unmasked": 0, "observed_unmasked": 0, "classification": "expected"},
        "process_exit_status": 0,
        "static_process_gate": {
            "wall_seconds": resources["wall_seconds"],
            "target_seconds": 180,
            "passed": True,
        },
        "total_latency_gate": total_gate,
        "preparation_build_target_seconds": 45,
        "preparation_build_target_waives_other_targets": False,
        "identities": exact_identities,
    }
    result["result_sha256"] = sha256_bytes(canonical_json_bytes(result))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--timing-csv", type=Path, required=True)
    parser.add_argument("--time-v", type=Path, required=True)
    parser.add_argument("--process-log", type=Path, required=True)
    parser.add_argument("--process-exit-status", type=int, required=True)
    parser.add_argument("--total-latency-seconds")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise ManifestError("refusing to replace an existing result")
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    result = build_result(
        raw,
        timing_csv=args.timing_csv.read_text(encoding="utf-8"),
        time_v=args.time_v.read_text(encoding="utf-8"),
        process_log=args.process_log.read_text(encoding="utf-8", errors="strict"),
        process_exit_status=args.process_exit_status,
        total_latency_seconds=args.total_latency_seconds,
    )
    atomic_write_json(args.output, result)
    print(f"validated result: {args.output}")
    print(f"result_sha256={result['result_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
