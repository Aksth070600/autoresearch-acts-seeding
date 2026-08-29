#!/usr/bin/env python3
"""Promote fully qualified LZ4 bytes to the canonical owned-static dataset."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from schema import (
    CANONICAL_PROJECT_GENESIS_COMMIT,
    CANONICAL_PROTOCOL_ID,
    ManifestError,
    atomic_write_json,
    canonical_dataset_id,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_dataset_directory,
)

EVIDENCE_SCHEMA = "acts-v4-owned-static-qualification-evidence-v1"


def _sha(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ManifestError(f"qualification evidence {field} is not SHA-256")
    return value


def validate_evidence(
    path: Path, manifest: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    evidence = json.loads(raw)
    if raw != canonical_json_bytes(evidence):
        raise ManifestError("qualification evidence is not canonical JSON")
    expected_keys = {
        "schema",
        "one_event_equality_sha256",
        "fifty_event_equality_sha256",
        "negative_qualification_sha256",
        "latency_result_sha256",
        "source_manifest_sha256",
        "build_manifest_sha256",
        "payload_sha256",
        "all_gates_passed",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_keys:
        raise ManifestError("qualification evidence shape mismatch")
    if (
        evidence["schema"] != EVIDENCE_SCHEMA
        or evidence["all_gates_passed"] is not True
    ):
        raise ManifestError("qualification evidence does not pass every gate")
    for field in expected_keys - {"schema", "all_gates_passed"}:
        _sha(evidence[field], field)
    identities = manifest["identities"]
    if evidence["source_manifest_sha256"] != identities["source_manifest_sha256"]:
        raise ManifestError("qualification source identity mismatch")
    if evidence["build_manifest_sha256"] != identities["build_manifest_sha256"]:
        raise ManifestError("qualification build identity mismatch")
    if evidence["payload_sha256"] != manifest["payload"]["sha256"]:
        raise ManifestError("qualification payload identity mismatch")
    return evidence, sha256_bytes(raw)


def canonicalize_manifest(qualification: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads(canonical_json_bytes(qualification))
    if manifest["dataset"]["event_count"] != 50:
        raise ManifestError("canonical publication requires 50 events")
    if manifest["payload"]["compression"] != {"algorithm": "lz4", "level": 4}:
        raise ManifestError("canonical publication requires LZ4 level 4")
    production = manifest["production"]
    if production["project_genesis_commit"] != CANONICAL_PROJECT_GENESIS_COMMIT:
        raise ManifestError("generation did not bind the canonical project Genesis")
    manifest["qualification"] = {
        "only": False,
        "canonical": True,
        "unresolved_captain_decisions": [],
    }
    manifest["protocol"] = {
        "id": CANONICAL_PROTOCOL_ID,
        "prefix": CANONICAL_PROTOCOL_ID,
    }
    production["project_genesis_is_canonical"] = True
    manifest["dataset"]["id"] = canonical_dataset_id(manifest)
    return manifest


def promote(
    source: Path, root: Path, evidence_path: Path
) -> tuple[Path, dict[str, Any], str, str]:
    source = source.resolve(strict=True)
    root = root.resolve(strict=True)
    qualification, _ = validate_dataset_directory(source, expected_events=50)
    _, evidence_hash = validate_evidence(
        evidence_path.resolve(strict=True), qualification
    )
    manifest = canonicalize_manifest(qualification)
    dataset_id = manifest["dataset"]["id"]
    destination = root / dataset_id
    if destination.exists() or destination.is_symlink():
        raise ManifestError(f"canonical dataset identity conflict: {destination}")

    publication = Path(tempfile.mkdtemp(prefix=f".{dataset_id}.publish-", dir=root))
    published_payload = publication / "payload.root"
    source_payload = source / "payload.root"
    try:
        os.replace(source_payload, published_payload)
        atomic_write_json(publication / "manifest.json", manifest)
        manifest_hash = sha256_file(publication / "manifest.json")
        sums = (
            f"{manifest_hash}  manifest.json\n"
            f"{manifest['payload']['sha256']}  payload.root\n"
        )
        (publication / "SHA256SUMS").write_text(sums, encoding="ascii")
        validate_dataset_directory(
            publication,
            expected_protocol_id=CANONICAL_PROTOCOL_ID,
            expected_dataset_id=dataset_id,
            expected_events=50,
        )
        for path in publication.iterdir():
            path.chmod(stat.S_IRUSR | stat.S_IRGRP)
        publication.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)
        os.replace(publication, destination)
    except BaseException:
        if published_payload.is_file() and not source_payload.exists():
            published_payload.chmod(stat.S_IRUSR | stat.S_IWUSR)
            os.replace(published_payload, source_payload)
        shutil.rmtree(publication, ignore_errors=True)
        raise
    return destination, manifest, manifest_hash, evidence_hash


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification-dataset", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--qualification-evidence", type=Path, required=True)
    parser.add_argument("--publication-record", type=Path, required=True)
    args = parser.parse_args()
    if args.publication_record.exists():
        raise ManifestError("refusing to replace publication record")
    destination, manifest, manifest_hash, evidence_hash = promote(
        args.qualification_dataset, args.canonical_root, args.qualification_evidence
    )
    record = {
        "schema": "acts-v4-owned-static-publication-v1",
        "protocol_id": CANONICAL_PROTOCOL_ID,
        "dataset_id": manifest["dataset"]["id"],
        "publication_path": str(destination),
        "manifest_sha256": manifest_hash,
        "manifest_identity_sha256": manifest["dataset"]["id"].rsplit("-", 1)[1],
        "payload_sha256": manifest["payload"]["sha256"],
        "qualification_evidence_sha256": evidence_hash,
        "identities": manifest["identities"],
    }
    atomic_write_json(args.publication_record, record)
    print(f"canonical_dataset={destination}")
    print(f"dataset_id={record['dataset_id']}")
    print(f"manifest_sha256={manifest_hash}")
    print(f"payload_sha256={record['payload_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
