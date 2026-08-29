#!/usr/bin/env python3
"""Delete the exact overlay objects so Ninja cannot trust copied timestamps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apply_overlay import verify_overlay
from schema import ManifestError, atomic_write_json, sha256_file

OBJECTS = (
    "Examples/Io/Root/CMakeFiles/ActsExamplesIoRoot.dir/src/OwnedSeedingDataset.cpp.o",
    "Python/Examples/CMakeFiles/ActsExamplesPythonBindings.dir/src/PythonSpecific.cpp.o",
    "Python/Examples/CMakeFiles/ActsExamplesPythonBindingsRoot.dir/src/plugins/Root.cpp.o",
)


def invalidate(source: Path, build: Path, evidence: Path | None = None) -> dict:
    source = source.resolve(strict=True)
    build = build.resolve(strict=True)
    verify_overlay(source)
    cache = build / "CMakeCache.txt"
    ninja = build / "build.ninja"
    if not cache.is_file() or not ninja.is_file():
        raise ManifestError("private build is not configured with Ninja")
    cache_text = cache.read_text(encoding="utf-8", errors="strict")
    expected_home = f"CMAKE_HOME_DIRECTORY:INTERNAL={source}"
    if expected_home not in cache_text:
        raise ManifestError("CMake source path differs from the private source")
    if str(source) not in ninja.read_text(encoding="utf-8", errors="strict"):
        raise ManifestError("Ninja graph does not reference the private source")

    entries = []
    for relative in OBJECTS:
        output = (build / relative).resolve(strict=False)
        if output != build / relative or build not in output.parents:
            raise ManifestError("unsafe Ninja output path")
        existed = output.is_file()
        if output.exists() and not existed:
            raise ManifestError(f"expected object is not a regular file: {relative}")
        before = sha256_file(output) if existed else None
        if existed:
            output.unlink()
        entries.append({"path": relative, "existed": existed, "before_sha256": before, "absent_after": not output.exists()})
    result = {
        "schema": "acts-v4-static-ninja-invalidation-v1",
        "strategy": "delete-exact-overlay-objects",
        "objects": entries,
    }
    if evidence is not None:
        atomic_write_json(evidence, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    print(json.dumps(invalidate(args.source, args.build, args.evidence), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
