#!/usr/bin/env python3
"""Write and validate a proposal-bound candidate source/build identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from apply_overlay import verify_overlay
from schema import (
    ACTS_COMMIT,
    CANONICAL_PROJECT_GENESIS_COMMIT,
    ManifestError,
    atomic_write_json,
    canonical_json_bytes,
    sha256_file,
)

SOURCE_SCHEMA = "acts-v4-static-candidate-source-identity-v1"
BUILD_SCHEMA = "acts-v4-static-candidate-build-identity-v1"


def _git(source: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        raise ManifestError(f"git command failed: {process.stderr.strip()}")
    return process.stdout


def _manifest_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _load_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise ManifestError(f"identity input is not canonical JSON: {path}")
    return value


def _load_self_hashed(path: Path, schema: str, key: str) -> tuple[dict[str, Any], str]:
    value = _load_canonical(path)
    if value.get("schema") != schema:
        raise ManifestError(f"identity schema mismatch: {path.name}")
    claimed = value.get(key)
    unhashed = dict(value)
    unhashed.pop(key, None)
    if not isinstance(claimed, str) or _manifest_hash(unhashed) != claimed:
        raise ManifestError(f"identity self-hash mismatch: {path.name}")
    return value, claimed


def _optimization_files(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise ManifestError(f"optimization tree is missing: {root}")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ManifestError(f"optimization tree contains a symlink: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = sha256_file(path)
    if not files:
        raise ManifestError("optimization tree is empty")
    return files


def _proposal(path: Path, implementation_commit: str) -> tuple[dict[str, Any], str]:
    proposal = _load_canonical(path)
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
    if set(proposal) != required or proposal["schema_version"] != "1.0.0":
        raise ManifestError("candidate proposal shape mismatch")
    if proposal["implementation_commit"] != implementation_commit:
        raise ManifestError("proposal implementation commit mismatch")
    if proposal["slot"] not in {1, 2, 3, 4}:
        raise ManifestError("proposal slot is invalid")
    if proposal["classification"] not in {"major", "minor", "combination"}:
        raise ManifestError("proposal classification is invalid")
    files = proposal["intended_files"]
    if not isinstance(files, list) or not files or files != sorted(set(files)):
        raise ManifestError("proposal intended files must be unique and sorted")
    if any(
        not isinstance(path_value, str)
        or not path_value.startswith("optimization-files/")
        or ".." in Path(path_value).parts
        for path_value in files
    ):
        raise ManifestError(
            "proposal intended file is outside the optimization surface"
        )
    return proposal, hashlib.sha256(canonical_json_bytes(proposal)).hexdigest()


def _artifact_files(build: Path) -> list[Path]:
    files = {build / "CMakeCache.txt", build / "build.ninja", build / ".ninja_deps"}
    for pattern in ("lib*/libActs*.so", "python/acts/**/*.so"):
        files.update(path for path in build.glob(pattern) if path.is_file())
    result = sorted(path for path in files if path.is_file())
    if not any(path.name == "libActsCore.so" for path in result):
        raise ManifestError("candidate build lacks ActsCore")
    if not any("ActsExamplesPythonBindings" in path.name for path in result):
        raise ManifestError("candidate build lacks Python bindings")
    return result


def write_candidate_identity(
    source: Path,
    build: Path,
    genesis_tree: Path,
    proposal_path: Path,
    implementation_commit: str,
    invalidation_path: Path,
    output: Path,
    preparation_build_seconds: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = source.resolve(strict=True)
    build = build.resolve(strict=True)
    genesis_tree = genesis_tree.resolve(strict=True)
    marker = verify_overlay(source)
    if _git(source, "rev-parse", "HEAD").strip() != ACTS_COMMIT:
        raise ManifestError("candidate ACTS source commit mismatch")
    proposal, proposal_hash = _proposal(
        proposal_path.resolve(strict=True), implementation_commit
    )
    genesis = _optimization_files(genesis_tree)
    intended = [
        path.removeprefix("optimization-files/") for path in proposal["intended_files"]
    ]
    candidate: dict[str, str] = {}
    changed: list[str] = []
    for relative, genesis_hash in genesis.items():
        path = source / relative
        if path.is_symlink() or not path.is_file():
            raise ManifestError(f"candidate source lacks Genesis file: {relative}")
        digest = sha256_file(path)
        candidate[relative] = digest
        if digest != genesis_hash:
            changed.append(relative)
    if changed != intended:
        raise ManifestError(
            f"candidate source change set differs from proposal: observed={changed}, intended={intended}"
        )

    status_paths: set[str] = set()
    for line in _git(
        source, "status", "--porcelain=v1", "--untracked-files=all"
    ).splitlines():
        if len(line) < 4 or " -> " in line:
            raise ManifestError("candidate ACTS status is malformed")
        status_paths.add(line[3:])
    expected_status = set(marker["target_sha256"]) | set(changed)
    if status_paths != expected_status:
        raise ManifestError(
            f"candidate ACTS source contains drift: {sorted(status_paths ^ expected_status)}"
        )

    invalidation = _load_canonical(invalidation_path.resolve(strict=True))
    if invalidation.get("changed_files") != proposal["intended_files"]:
        raise ManifestError("Ninja invalidation does not cover the proposal files")
    if invalidation.get("all_affected_outputs_absent") is not True:
        raise ManifestError("Ninja invalidation did not remove every affected output")
    invalidation_hash = sha256_file(invalidation_path)
    optimization_tree_hash = hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
    source_manifest: dict[str, Any] = {
        "schema": SOURCE_SCHEMA,
        "acts_commit": ACTS_COMMIT,
        "project_genesis_commit": CANONICAL_PROJECT_GENESIS_COMMIT,
        "implementation_commit": implementation_commit,
        "candidate": proposal["candidate"],
        "mechanism_key": proposal["mechanism_key"],
        "proposal_sha256": proposal_hash,
        "overlay_manifest_sha256": marker["overlay_manifest_sha256"],
        "changed_files": proposal["intended_files"],
        "optimization_file_sha256": candidate,
        "optimization_tree_sha256": optimization_tree_hash,
    }
    source_manifest["source_manifest_sha256"] = _manifest_hash(source_manifest)

    artifacts = {
        path.relative_to(build).as_posix(): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in _artifact_files(build)
    }
    try:
        preparation_value = float(preparation_build_seconds)
    except ValueError as error:
        raise ManifestError("preparation/build duration is malformed") from error
    if not preparation_value >= 0:
        raise ManifestError("preparation/build duration is negative")
    build_manifest: dict[str, Any] = {
        "schema": BUILD_SCHEMA,
        "acts_commit": ACTS_COMMIT,
        "source_manifest_sha256": source_manifest["source_manifest_sha256"],
        "proposal_sha256": proposal_hash,
        "top_target": "ActsPythonBindings",
        "max_build_jobs": 8,
        "ninja_invalidation_sha256": invalidation_hash,
        "preparation_build_seconds": preparation_build_seconds,
        "preparation_build_target_seconds": 45,
        "preparation_build_target_passed": preparation_value <= 45,
        "artifacts": artifacts,
    }
    build_manifest["build_manifest_sha256"] = _manifest_hash(build_manifest)
    output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output / "candidate-source-manifest.json", source_manifest)
    atomic_write_json(output / "candidate-build-manifest.json", build_manifest)
    return source_manifest, build_manifest


def validate_candidate_build(
    source: Path, build: Path, identities: Path, expected_proposal_sha256: str
) -> tuple[dict[str, str], dict[str, Any]]:
    source = source.resolve(strict=True)
    build = build.resolve(strict=True)
    identities = identities.resolve(strict=True)
    marker = verify_overlay(source)
    source_manifest, source_hash = _load_self_hashed(
        identities / "candidate-source-manifest.json",
        SOURCE_SCHEMA,
        "source_manifest_sha256",
    )
    build_manifest, build_hash = _load_self_hashed(
        identities / "candidate-build-manifest.json",
        BUILD_SCHEMA,
        "build_manifest_sha256",
    )
    if source_manifest["proposal_sha256"] != expected_proposal_sha256:
        raise ManifestError("loaded candidate proposal identity mismatch")
    if source_manifest["overlay_manifest_sha256"] != marker["overlay_manifest_sha256"]:
        raise ManifestError("candidate overlay identity mismatch")
    if build_manifest["source_manifest_sha256"] != source_hash:
        raise ManifestError("candidate source/build identity mismatch")
    if build_manifest["proposal_sha256"] != expected_proposal_sha256:
        raise ManifestError("candidate build proposal identity mismatch")
    for relative, record in build_manifest["artifacts"].items():
        path = build / relative
        if path.is_symlink() or not path.is_file():
            raise ManifestError(f"candidate build artifact is missing: {relative}")
        if (
            path.stat().st_size != record["size_bytes"]
            or sha256_file(path) != record["sha256"]
        ):
            raise ManifestError(
                f"candidate build artifact identity mismatch: {relative}"
            )
    return {
        "source_manifest_sha256": source_hash,
        "build_manifest_sha256": build_hash,
        "overlay_manifest_sha256": marker["overlay_manifest_sha256"],
        "proposal_sha256": expected_proposal_sha256,
    }, build_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--genesis-tree", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--implementation-commit", required=True)
    parser.add_argument("--invalidation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preparation-build-seconds", required=True)
    args = parser.parse_args()
    source, build = write_candidate_identity(
        args.source,
        args.build,
        args.genesis_tree,
        args.proposal,
        args.implementation_commit,
        args.invalidation,
        args.output,
        args.preparation_build_seconds,
    )
    print(f"candidate_source_manifest_sha256={source['source_manifest_sha256']}")
    print(f"candidate_build_manifest_sha256={build['build_manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
