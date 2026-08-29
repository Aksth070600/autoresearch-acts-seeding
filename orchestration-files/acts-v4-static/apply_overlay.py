#!/usr/bin/env python3
"""Apply the content-addressed static-v4 overlay to a private ACTS copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from schema import ACTS_COMMIT, ManifestError, atomic_write_json, canonical_json_bytes, sha256_file

MODULE = Path(__file__).resolve().parent
MANIFEST_PATH = MODULE / "overlay-manifest.json"
MARKER = ".acts-v4-static-overlay.json"


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ManifestError(f"unsafe overlay path: {value!r}")
    return path


def _load_overlay() -> tuple[dict[str, Any], str]:
    raw = MANIFEST_PATH.read_bytes()
    manifest = json.loads(raw)
    if raw != canonical_json_bytes(manifest):
        raise ManifestError("overlay manifest is not canonical JSON")
    if set(manifest) != {"schema", "acts_commit", "patch", "modified_files", "added_files"}:
        raise ManifestError("overlay manifest shape mismatch")
    if manifest["schema"] != "acts-v4-static-overlay-v1" or manifest["acts_commit"] != ACTS_COMMIT:
        raise ManifestError("overlay ACTS/schema identity mismatch")
    return manifest, hashlib.sha256(raw).hexdigest()


def _git(source: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        raise ManifestError(f"git {' '.join(arguments)} failed: {process.stderr.strip()}")
    return process.stdout.strip()


def apply_overlay(source: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if not source.is_dir() or source.is_symlink():
        raise ManifestError("ACTS source must be a regular directory")
    if _git(source, "rev-parse", "HEAD") != ACTS_COMMIT:
        raise ManifestError("private ACTS copy is not at the pinned commit")
    if (source / MARKER).exists():
        raise ManifestError("overlay marker already exists")

    manifest, manifest_hash = _load_overlay()
    patch = manifest["patch"]
    patch_path = MODULE / _safe_relative(patch["path"])
    if sha256_file(patch_path) != patch["sha256"]:
        raise ManifestError("overlay patch hash mismatch")

    for entry in manifest["modified_files"]:
        target = source / _safe_relative(entry["path"])
        if target.is_symlink() or not target.is_file():
            raise ManifestError(f"overlay target is not a regular file: {entry['path']}")
        if sha256_file(target) != entry["before_sha256"]:
            raise ManifestError(f"overlay base hash mismatch: {entry['path']}")
    for entry in manifest["added_files"]:
        project_source = MODULE / _safe_relative(entry["source"])
        target = source / _safe_relative(entry["target"])
        if sha256_file(project_source) != entry["sha256"]:
            raise ManifestError(f"project overlay source hash mismatch: {entry['source']}")
        if target.exists() or target.is_symlink():
            raise ManifestError(f"overlay addition already exists: {entry['target']}")

    process = subprocess.run(
        ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch_path)],
        cwd=source,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if process.returncode != 0:
        raise ManifestError(f"overlay patch failed:\n{process.stdout}")

    for entry in manifest["added_files"]:
        project_source = MODULE / _safe_relative(entry["source"])
        target = source / _safe_relative(entry["target"])
        target.parent.mkdir(parents=True, exist_ok=True)
        with project_source.open("rb") as input_stream, target.open("xb") as output_stream:
            shutil.copyfileobj(input_stream, output_stream)
            output_stream.flush()
            os.fsync(output_stream.fileno())

    target_hashes: dict[str, str] = {}
    for entry in manifest["modified_files"]:
        target = source / _safe_relative(entry["path"])
        actual = sha256_file(target)
        if actual != entry["after_sha256"]:
            raise ManifestError(f"patched target hash mismatch: {entry['path']}")
        target_hashes[entry["path"]] = actual
    for entry in manifest["added_files"]:
        target = source / _safe_relative(entry["target"])
        actual = sha256_file(target)
        if actual != entry["sha256"]:
            raise ManifestError(f"added target hash mismatch: {entry['target']}")
        target_hashes[entry["target"]] = actual

    marker = {
        "schema": "acts-v4-static-applied-overlay-v1",
        "acts_commit": ACTS_COMMIT,
        "overlay_manifest_sha256": manifest_hash,
        "target_sha256": dict(sorted(target_hashes.items())),
    }
    atomic_write_json(source / MARKER, marker)
    return marker


def _expected_target_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for entry in manifest["modified_files"]:
        expected[entry["path"]] = entry["after_sha256"]
    for entry in manifest["added_files"]:
        expected[entry["target"]] = entry["sha256"]
    return dict(sorted(expected.items()))


def refresh_overlay_marker(source: Path) -> dict[str, Any]:
    """Rebind a compile-iteration tree after every target matches a new manifest."""
    source = source.resolve(strict=True)
    marker_path = source / MARKER
    if not marker_path.is_file() or marker_path.is_symlink():
        raise ManifestError("an existing regular overlay marker is required")
    manifest, manifest_hash = _load_overlay()
    expected = _expected_target_hashes(manifest)
    for relative, digest in expected.items():
        path = source / _safe_relative(relative)
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise ManifestError(f"cannot refresh marker with target drift: {relative}")
    marker = {
        "schema": "acts-v4-static-applied-overlay-v1",
        "acts_commit": ACTS_COMMIT,
        "overlay_manifest_sha256": manifest_hash,
        "target_sha256": expected,
    }
    atomic_write_json(marker_path, marker)
    return marker


def verify_overlay(source: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    marker_path = source / MARKER
    marker_raw = marker_path.read_bytes()
    marker = json.loads(marker_raw)
    if marker_raw != canonical_json_bytes(marker):
        raise ManifestError("overlay marker is not canonical JSON")
    manifest, manifest_hash = _load_overlay()
    if marker.get("schema") != "acts-v4-static-applied-overlay-v1":
        raise ManifestError("overlay marker schema mismatch")
    if marker.get("acts_commit") != ACTS_COMMIT or marker.get("overlay_manifest_sha256") != manifest_hash:
        raise ManifestError("overlay marker identity mismatch")
    expected = _expected_target_hashes(manifest)
    if marker.get("target_sha256") != expected:
        raise ManifestError("overlay marker target manifest mismatch")
    for relative, digest in expected.items():
        path = source / _safe_relative(relative)
        if path.is_symlink() or not path.is_file() or sha256_file(path) != digest:
            raise ManifestError(f"applied overlay file drift: {relative}")
    return marker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("apply", "refresh-marker", "verify"))
    parser.add_argument("--source", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "apply":
        marker = apply_overlay(args.source)
    elif args.mode == "refresh-marker":
        marker = refresh_overlay_marker(args.source)
    else:
        marker = verify_overlay(args.source)
    print(canonical_json_bytes(marker).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
