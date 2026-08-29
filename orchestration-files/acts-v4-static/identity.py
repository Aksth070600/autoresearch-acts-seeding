#!/usr/bin/env python3
"""Runtime identity checks shared by the dataset builder and static runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from apply_overlay import verify_overlay
from schema import ACTS_COMMIT, ManifestError, canonical_json_bytes, sha256_file

MODULE = Path(__file__).resolve().parent


def _load_self_hashed(path: Path, key: str, schema: str) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if raw != canonical_json_bytes(value) or value.get("schema") != schema:
        raise ManifestError(f"invalid identity manifest: {path.name}")
    claimed = value.get(key)
    if not isinstance(claimed, str):
        raise ManifestError(f"identity manifest lacks {key}")
    unhashed = dict(value)
    unhashed.pop(key)
    actual = hashlib.sha256(canonical_json_bytes(unhashed)).hexdigest()
    if actual != claimed:
        raise ManifestError(f"identity manifest self-hash mismatch: {path.name}")
    return value, claimed


def validate_private_build(
    source: Path, build: Path, identities: Path
) -> dict[str, str]:
    source = source.resolve(strict=True)
    build = build.resolve(strict=True)
    identities = identities.resolve(strict=True)
    marker = verify_overlay(source)
    source_manifest, source_hash = _load_self_hashed(
        identities / "source-manifest.json",
        "source_manifest_sha256",
        "acts-v4-static-source-identity-v1",
    )
    build_manifest, build_hash = _load_self_hashed(
        identities / "build-manifest.json",
        "build_manifest_sha256",
        "acts-v4-static-build-identity-v1",
    )
    if source_manifest["acts_commit"] != ACTS_COMMIT:
        raise ManifestError("source manifest ACTS mismatch")
    if source_manifest["overlay_manifest_sha256"] != marker["overlay_manifest_sha256"]:
        raise ManifestError("source manifest overlay mismatch")
    if build_manifest["acts_commit"] != ACTS_COMMIT or build_manifest["source_manifest_sha256"] != source_hash:
        raise ManifestError("build/source identity mismatch")
    if build_manifest["top_target"] != "ActsPythonBindings" or build_manifest["max_build_jobs"] != 8:
        raise ManifestError("build target or resource identity drift")
    for relative, record in build_manifest["artifacts"].items():
        path = build / relative
        if path.is_symlink() or not path.is_file():
            raise ManifestError(f"build artifact is missing: {relative}")
        if path.stat().st_size != record["size_bytes"] or sha256_file(path) != record["sha256"]:
            raise ManifestError(f"build artifact hash mismatch: {relative}")
    return {
        "source_manifest_sha256": source_hash,
        "build_manifest_sha256": build_hash,
        "overlay_manifest_sha256": marker["overlay_manifest_sha256"],
    }


def input_identities(geometry_dir: Path) -> dict[str, str]:
    geometry_dir = geometry_dir.resolve(strict=True)
    files = {
        "geometry_tgeo_sha256": geometry_dir / "itk-hgtd/ATLAS-ITk-HGTD.tgeo.root",
        "geometry_material_sha256": geometry_dir / "itk-hgtd/material-maps-ITk-HGTD.json",
        "field_sha256": geometry_dir / "bfield/ATLAS-BField-xyz.root",
        "digitization_sha256": geometry_dir / "itk-hgtd/itk-smearing-config.json",
        "pixel_geometry_selection_sha256": geometry_dir / "itk-hgtd/geoSelection-ITk.json",
    }
    result = {key: sha256_file(path) for key, path in files.items()}
    itk_source = Path(__import__("acts.examples.itk", fromlist=["__file__"]).__file__)
    digest = hashlib.sha256()
    digest.update(itk_source.read_bytes())
    digest.update(b"\0InputSpacePointsType.PixelSpacePoints")
    result["seeding_config_sha256"] = digest.hexdigest()
    return result


def source_file_identities() -> dict[str, str]:
    source = MODULE / "cpp/src/OwnedSeedingDataset.cpp"
    return {
        "writer_source_sha256": sha256_file(source),
        "reader_source_sha256": sha256_file(source),
        "builder_sha256": sha256_file(MODULE / "build_dataset.py"),
    }
