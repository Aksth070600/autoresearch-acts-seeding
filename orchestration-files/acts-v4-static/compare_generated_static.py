#!/usr/bin/env python3
"""Require exact generated/static identity for all scientific diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from schema import ManifestError, atomic_write_json, canonical_json_bytes, sha256_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--static", type=Path, required=True)
    parser.add_argument("--static-diagnostics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ManifestError("refusing to replace equality proof")
    generated = json.loads(args.generated.read_text(encoding="utf-8"))
    static = json.loads(args.static.read_text(encoding="utf-8"))
    static_diagnostics = json.loads(args.static_diagnostics.read_text(encoding="utf-8"))
    for key in ("event_count", "completed_event_ids", "input_event_hashes", "stats"):
        if generated[key] != static[key]:
            raise ManifestError(f"generated/static mismatch: {key}")
    if generated["diagnostics"] != static_diagnostics:
        raise ManifestError(
            "generated/static mismatch in ordered seeds, parameters, tracks, or matcher"
        )
    for key in (
        "raw_seed_count",
        "estimated_seed_count",
        "estimated_parameter_count",
        "converted_track_count",
        "matcher_classification_counts",
        "ordered_diagnostics_sha256",
    ):
        if generated["diagnostics"][key] != static["diagnostics"][key]:
            raise ManifestError(f"generated/static aggregate mismatch: {key}")
    proof = {
        "schema": "acts-v4-static-generated-equality-v1",
        "events": generated["event_count"],
        "input_event_hashes": generated["input_event_hashes"],
        "stats": generated["stats"],
        "diagnostics": generated["diagnostics"],
    }
    proof["proof_sha256"] = sha256_bytes(canonical_json_bytes(proof))
    atomic_write_json(args.output, proof)
    print(f"exact_generated_static_equality=passed events={proof['events']}")
    print(f"proof_sha256={proof['proof_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
