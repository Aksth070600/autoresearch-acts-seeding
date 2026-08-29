#!/usr/bin/env python3
"""Write deterministic source and private-build identity manifests."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from apply_overlay import verify_overlay
from schema import ACTS_COMMIT, ManifestError, atomic_write_json, canonical_json_bytes, sha256_file


def _git(source: Path, *arguments: str, binary: bool = False):
    process = subprocess.run(
        ["git", "-C", str(source), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    if process.returncode != 0:
        error = process.stderr if not binary else process.stderr.decode(errors="replace")
        raise ManifestError(f"git command failed: {error.strip()}")
    return process.stdout


def _manifest_hash(value: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_identities(source: Path, build: Path, output: Path) -> tuple[dict, dict]:
    source = source.resolve(strict=True)
    build = build.resolve(strict=True)
    marker = verify_overlay(source)
    if _git(source, "rev-parse", "HEAD").strip() != ACTS_COMMIT:
        raise ManifestError("source commit changed")

    # The dotfile marker is ignored by the pinned ACTS repository. It is
    # validated independently by verify_overlay and is absent from git status.
    overlay_paths = set(marker["target_sha256"])
    status = _git(source, "status", "--porcelain=v1", "--untracked-files=all")
    observed_paths: set[str] = set()
    for line in status.splitlines():
        if len(line) < 4:
            raise ManifestError("malformed git status line")
        path = line[3:]
        if " -> " in path:
            raise ManifestError("renamed source path is not allowed")
        observed_paths.add(path)
    if observed_paths != overlay_paths:
        raise ManifestError(
            f"private source contains non-overlay drift: {sorted(observed_paths ^ overlay_paths)}"
        )

    diff = _git(source, "diff", "--binary", "--no-ext-diff", binary=True)
    source_manifest = {
        "schema": "acts-v4-static-source-identity-v1",
        "acts_commit": ACTS_COMMIT,
        "overlay_manifest_sha256": marker["overlay_manifest_sha256"],
        "overlay_target_sha256": marker["target_sha256"],
        "git_diff_sha256": hashlib.sha256(diff).hexdigest(),
    }
    source_manifest["source_manifest_sha256"] = _manifest_hash(source_manifest)

    required = [build / "CMakeCache.txt", build / "build.ninja"]
    for path in required:
        if not path.is_file():
            raise ManifestError(f"missing build control: {path.name}")
    candidates: set[Path] = set(required)
    patterns = (
        "lib*/libActsCore.so",
        "lib*/libActsExamplesIoRoot.so",
        "python/acts/examples/ActsExamplesPythonBindings*.so",
    )
    for pattern in patterns:
        candidates.update(path for path in build.glob(pattern) if path.is_file())
    if not any(path.name == "libActsExamplesIoRoot.so" for path in candidates):
        raise ManifestError("owned ROOT library was not built")
    if not any("ActsExamplesPythonBindingsRoot" in path.name for path in candidates):
        raise ManifestError("owned ROOT Python binding was not built")
    if not any(path.name.startswith("ActsExamplesPythonBindings.cpython") for path in candidates):
        raise ManifestError("main Python binding with exact stats was not built")

    artifacts = {
        str(path.relative_to(build)): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(candidates)
    }
    build_manifest = {
        "schema": "acts-v4-static-build-identity-v1",
        "acts_commit": ACTS_COMMIT,
        "source_manifest_sha256": source_manifest["source_manifest_sha256"],
        "top_target": "ActsPythonBindings",
        "max_build_jobs": 8,
        "artifacts": artifacts,
    }
    build_manifest["build_manifest_sha256"] = _manifest_hash(build_manifest)

    output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(output / "source-manifest.json", source_manifest)
    atomic_write_json(output / "build-manifest.json", build_manifest)
    return source_manifest, build_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, build = write_identities(args.source, args.build, args.output)
    print(f"source_manifest_sha256={source['source_manifest_sha256']}")
    print(f"build_manifest_sha256={build['build_manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
