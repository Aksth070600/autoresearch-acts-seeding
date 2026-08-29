#!/usr/bin/env python3
"""Validate generation outcome and atomically publish three qualification files."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path

from schema import (
    ManifestError,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    validate_dataset_directory,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--process-log", type=Path, required=True)
    parser.add_argument("--process-exit-status", type=int, required=True)
    return parser.parse_args()


def completion(log: str) -> tuple[int, int]:
    events = re.findall(r"Processed (\d+) events in", log)
    encountered = re.findall(r"Encountered (\d+) unmasked FPEs", log)
    no_fpe = re.findall(r"No unmasked FPEs encountered", log)
    if len(events) != 1 or len(encountered) + len(no_fpe) != 1:
        raise ManifestError("generation log lacks one completion/FPE summary")
    return int(events[0]), int(encountered[0]) if encountered else 0


def main() -> int:
    args = parse_args()
    staging = args.staging.resolve(strict=True)
    destination = args.destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ManifestError("refusing to replace an existing dataset")
    if destination.parent.resolve(strict=True) != staging.parent.resolve(strict=True):
        raise ManifestError("staging and destination must share an atomic-rename parent")
    if args.process_exit_status != 0:
        raise ManifestError("dataset builder process did not exit successfully")
    draft_path = staging / "production-draft.json"
    payload_path = staging / "payload.root"
    if not draft_path.is_file() or not payload_path.is_file():
        raise ManifestError("staging lacks a complete draft or payload")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    processed, fpes = completion(args.process_log.read_text(encoding="utf-8"))
    expected = draft["dataset"]["event_count"]
    if processed != expected:
        raise ManifestError("generation did not complete every event")

    production = dict(draft["production_without_process_outcome"])
    production.update(
        {
            "exit_status": 0,
            "completed_event_ids": list(range(expected)),
            "unmasked_fpes": fpes,
        }
    )
    manifest = {
        "schema": draft["schema"],
        "qualification": draft["qualification"],
        "protocol": draft["protocol"],
        "dataset": draft["dataset"],
        "payload": draft["payload_transport"],
        "production": production,
        "identities": draft["identities"],
        "contracts": draft["contracts"],
    }

    publication = destination.with_name(f".{destination.name}.publish-{os.getpid()}")
    if publication.exists() or publication.is_symlink():
        raise ManifestError("publication staging path already exists")
    publication.mkdir(mode=0o750)
    published_payload = publication / "payload.root"
    try:
        os.replace(payload_path, published_payload)
        atomic_write_json(publication / "manifest.json", manifest)
        manifest_hash = sha256_bytes(canonical_json_bytes(manifest))
        sums = (
            f"{manifest_hash}  manifest.json\n"
            f"{manifest['payload']['sha256']}  payload.root\n"
        )
        (publication / "SHA256SUMS").write_text(sums, encoding="ascii")
        validate_dataset_directory(
            publication,
            expected_protocol_id=manifest["protocol"]["id"],
            expected_dataset_id=manifest["dataset"]["id"],
            expected_events=expected,
        )
        os.replace(publication, destination)
    except BaseException:
        if published_payload.is_file() and not payload_path.exists():
            os.replace(published_payload, payload_path)
        shutil.rmtree(publication, ignore_errors=True)
        raise
    print(f"qualification_dataset={destination}")
    print(f"manifest_sha256={manifest_hash}")
    print(f"payload_sha256={manifest['payload']['sha256']}")
    print(f"generation_unmasked_fpes={fpes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
