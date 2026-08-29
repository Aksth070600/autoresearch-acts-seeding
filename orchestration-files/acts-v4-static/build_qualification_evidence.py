#!/usr/bin/env python3
"""Bind all canonical-production qualification gates before publication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from promote_dataset import EVIDENCE_SCHEMA
from schema import (
    ManifestError,
    atomic_write_json,
    sha256_file,
    validate_dataset_directory,
)


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestError(
            f"cannot read qualification evidence {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise ManifestError(f"qualification evidence is not an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--one-event-equality", type=Path, required=True)
    parser.add_argument("--fifty-event-equality", type=Path, required=True)
    parser.add_argument("--negative-log", type=Path, required=True)
    parser.add_argument("--latency-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ManifestError("refusing to replace qualification evidence")

    manifest, _ = validate_dataset_directory(args.dataset, expected_events=50)
    one = load(args.one_event_equality)
    fifty = load(args.fifty_event_equality)
    latency = load(args.latency_result)
    if (
        one.get("schema") != "acts-v4-static-generated-equality-v1"
        or one.get("events") != 1
    ):
        raise ManifestError("one-event generated/static equality proof is invalid")
    if (
        fifty.get("schema") != "acts-v4-static-generated-equality-v1"
        or fifty.get("events") != 50
    ):
        raise ManifestError("50-event generated/static equality proof is invalid")
    expected_hashes = [
        event["semantic_sha256"] for event in manifest["dataset"]["events"]
    ]
    if fifty.get("input_event_hashes") != expected_hashes:
        raise ManifestError("50-event equality proof differs from publication payload")
    if latency.get("schema") != "acts-seeding-v4-owned-static-result-v1":
        raise ManifestError("latency result schema mismatch")
    if (
        latency.get("events") != 50
        or latency.get("input_event_hashes") != expected_hashes
    ):
        raise ManifestError("latency result differs from publication payload")
    if latency.get("stats") != fifty.get("stats"):
        raise ManifestError("latency result exact counters differ from equality proof")
    if latency.get("static_process_gate", {}).get("passed") is not True:
        raise ManifestError("static latency did not pass 180 seconds")

    negative_text = args.negative_log.read_text(encoding="utf-8")
    expected_cases = (
        "payload-byte-tamper",
        "manifest-hash-tamper",
        "protocol-drift",
        "malformed-csr",
        "non-finite",
        "unresolved-geometry",
        "unresolved-source",
        "unresolved-truth",
        "barcode-integer-range",
        "generation-process-enum",
        "simulation-outcome-enum",
        "map-inversion",
    )
    for case in expected_cases:
        if f"negative_case={case} rejected=ok partial_output=none" not in negative_text:
            raise ManifestError(f"negative qualification lacks passing case: {case}")
    if "negative_qualification=passed cases=12" not in negative_text:
        raise ManifestError("negative qualification completion is missing")

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "one_event_equality_sha256": sha256_file(args.one_event_equality),
        "fifty_event_equality_sha256": sha256_file(args.fifty_event_equality),
        "negative_qualification_sha256": sha256_file(args.negative_log),
        "latency_result_sha256": sha256_file(args.latency_result),
        "source_manifest_sha256": manifest["identities"]["source_manifest_sha256"],
        "build_manifest_sha256": manifest["identities"]["build_manifest_sha256"],
        "payload_sha256": manifest["payload"]["sha256"],
        "all_gates_passed": True,
    }
    atomic_write_json(args.output, evidence)
    print(f"canonical_qualification=passed evidence={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
