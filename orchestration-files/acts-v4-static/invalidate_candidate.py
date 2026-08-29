#!/usr/bin/env python3
"""Delete every Ninja object affected by proposal-bound candidate files."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from schema import ManifestError, atomic_write_json, sha256_file


def _run(build: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["ninja", "-C", str(build), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        raise ManifestError(
            f"Ninja {' '.join(arguments)} failed: {(process.stderr or process.stdout).strip()}"
        )
    return process.stdout


def _dependency_outputs(build: Path) -> dict[Path, set[str]]:
    result: dict[Path, set[str]] = {}
    current: str | None = None
    for line in _run(build, "-t", "deps").splitlines():
        if line and not line[0].isspace() and ":" in line:
            current = line.split(":", 1)[0]
            continue
        if current is None or not line.startswith("    "):
            continue
        dependency = Path(line.strip()).resolve(strict=False)
        result.setdefault(dependency, set()).add(current)
    return result


def invalidate(
    source: Path, build: Path, genesis_tree: Path, changed_files: list[str]
) -> dict:
    source = source.resolve(strict=True)
    build = build.resolve(strict=True)
    genesis_tree = genesis_tree.resolve(strict=True)
    cache = build / "CMakeCache.txt"
    ninja_file = build / "build.ninja"
    if not cache.is_file() or not ninja_file.is_file():
        raise ManifestError("candidate build is not configured with Ninja")
    if f"CMAKE_HOME_DIRECTORY:INTERNAL={source}" not in cache.read_text(
        encoding="utf-8", errors="strict"
    ):
        raise ManifestError("candidate CMake source path mismatch")
    if not changed_files or changed_files != sorted(set(changed_files)):
        raise ManifestError("changed files must be unique and sorted")

    dependencies = _dependency_outputs(build)
    records = []
    all_outputs: set[str] = set()
    for project_relative in changed_files:
        path = Path(project_relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not project_relative.startswith("optimization-files/")
        ):
            raise ManifestError(
                f"candidate file is outside optimization surface: {project_relative}"
            )
        relative = Path(project_relative).relative_to("optimization-files")
        genesis_path = genesis_tree / relative
        source_path = source / relative
        if not genesis_path.is_file() or not source_path.is_file():
            raise ManifestError(
                f"candidate or Genesis source is missing: {project_relative}"
            )
        if sha256_file(genesis_path) == sha256_file(source_path):
            raise ManifestError(
                f"candidate file does not differ from Genesis: {project_relative}"
            )
        outputs = sorted(dependencies.get(source_path.resolve(), set()))
        if not outputs:
            query = _run(build, "-t", "query", str(source_path))
            in_outputs = False
            for line in query.splitlines():
                stripped = line.strip()
                if stripped == "outputs:":
                    in_outputs = True
                    continue
                if in_outputs and line.startswith("    "):
                    outputs.append(stripped)
                elif in_outputs and stripped:
                    break
        outputs = sorted(
            output for output in set(outputs) if output.endswith((".o", ".obj"))
        )
        if not outputs:
            raise ManifestError(
                f"Ninja dependency proof is missing: {project_relative}"
            )
        all_outputs.update(outputs)
        records.append(
            {
                "file": project_relative,
                "genesis_sha256": sha256_file(genesis_path),
                "candidate_sha256": sha256_file(source_path),
                "affected_outputs": outputs,
            }
        )

    removed = []
    for relative in sorted(all_outputs):
        output = (build / relative).resolve(strict=False)
        if output != build / relative or build not in output.parents:
            raise ManifestError(f"unsafe Ninja output: {relative}")
        if output.exists() and not output.is_file():
            raise ManifestError(f"Ninja output is not a regular file: {relative}")
        existed = output.is_file()
        digest = sha256_file(output) if existed else None
        if existed:
            output.unlink()
        removed.append(
            {
                "path": relative,
                "existed": existed,
                "before_sha256": digest,
                "absent_after": not output.exists(),
            }
        )
    if not removed or not all(record["absent_after"] for record in removed):
        raise ManifestError("candidate dependency invalidation is incomplete")
    return {
        "schema": "acts-v4-static-candidate-ninja-invalidation-v1",
        "strategy": "delete-all-ninja-deps-affected-objects",
        "changed_files": changed_files,
        "dependencies": records,
        "removed_outputs": removed,
        "all_affected_outputs_absent": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--genesis-tree", type=Path, required=True)
    parser.add_argument("--changed-file", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ManifestError("refusing to replace invalidation evidence")
    result = invalidate(
        args.source,
        args.build,
        args.genesis_tree,
        sorted(args.changed_file),
    )
    atomic_write_json(args.output, result)
    print(f"candidate_invalidated_outputs={len(result['removed_outputs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
