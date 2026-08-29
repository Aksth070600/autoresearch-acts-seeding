#!/usr/bin/env python3
"""Inspect and hash the complete loaded ACTS shared-object closure."""

from __future__ import annotations

import re
from pathlib import Path

from schema import ManifestError, sha256_file

_SHARED_OBJECT = re.compile(r"\.so(?:\.|$)")


def _is_acts_object(path: Path) -> bool:
    name = path.name
    if _SHARED_OBJECT.search(name) is None:
        return False
    return name.startswith("libActs") or (
        name.startswith("Acts") and "PythonBindings" in name
    )


def loaded_acts_dsos(
    build: Path, *, maps_path: Path = Path("/proc/self/maps")
) -> dict[str, str]:
    """Return all loaded ACTS objects, rejecting any outside ``build``."""
    build = build.resolve(strict=True)
    paths: set[Path] = set()
    for line in maps_path.read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) < 6 or not fields[5].startswith("/"):
            continue
        mapped = fields[5]
        deleted = mapped.endswith(" (deleted)")
        path_text = mapped.removesuffix(" (deleted)")
        unresolved = Path(path_text)
        if not _is_acts_object(unresolved):
            continue
        if deleted:
            raise ManifestError(f"loaded ACTS object was deleted: {path_text}")
        path = unresolved.resolve(strict=True)
        if build != path and build not in path.parents:
            raise ManifestError(
                f"loaded ACTS object is outside validated private build: {path}"
            )
        if not path.is_file():
            raise ManifestError(f"loaded ACTS object is not a regular file: {path}")
        paths.add(path)
    if not paths or not any(path.name == "libActsCore.so" for path in paths):
        raise ManifestError("loaded private ACTS DSO closure is missing ActsCore")
    return {
        path.relative_to(build).as_posix(): sha256_file(path)
        for path in sorted(paths)
    }
