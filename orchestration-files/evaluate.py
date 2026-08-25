#!/usr/bin/env python3
"""Run controlled ACTS Seeding2 development or evaluation stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPTIMIZATION_ROOT = PROJECT_ROOT / "optimization-files"
RECORDS_ROOT = PROJECT_ROOT / "Records"
HEPP_HELPER = PROJECT_ROOT / "orchestration-files" / "HEPP-files" / "run-hepp-helper.sh"
EXPORT_OPTIMIZATION = PROJECT_ROOT / "orchestration-files" / "HEPP-files" / "export-optimization-files.sh"

ALLOWED_PATHS = {
    "Core/include/Acts/Seeding2/BroadTripletSeedFilter.hpp",
    "Core/include/Acts/Seeding2/CylindricalSpacePointGrid2.hpp",
    "Core/include/Acts/Seeding2/DoubletSeedFinder.hpp",
    "Core/include/Acts/Seeding2/ITripletSeedFilter.hpp",
    "Core/include/Acts/Seeding2/TripletSeedFinder.hpp",
    "Core/include/Acts/Seeding2/TripletSeeder.hpp",
    "Core/include/Acts/Seeding2/detail/CandidatesForMiddleSp2.hpp",
    "Core/src/Seeding2/BroadTripletSeedFilter.cpp",
    "Core/src/Seeding2/CylindricalSpacePointGrid2.cpp",
    "Core/src/Seeding2/DoubletSeedFinder.cpp",
    "Core/src/Seeding2/TripletSeedFinder.cpp",
    "Core/src/Seeding2/TripletSeeder.cpp",
    "Core/src/Seeding2/detail/CandidatesForMiddleSp2.cpp",
    "Core/include/Acts/EventData/SpacePointColumnProxy2.hpp",
    "Core/include/Acts/EventData/SpacePointColumns.hpp",
    "Core/include/Acts/EventData/SpacePointContainer2.hpp",
    "Core/include/Acts/EventData/SpacePointContainer2.ipp",
    "Core/include/Acts/EventData/SpacePointProxy2.hpp",
    "Core/include/Acts/Seeding/BinnedGroup.hpp",
    "Core/include/Acts/Seeding/BinnedGroup.ipp",
    "Core/include/Acts/Seeding/BinnedGroupIterator.hpp",
    "Core/include/Acts/Seeding/BinnedGroupIterator.ipp",
    "Core/include/Acts/Utilities/GridBinFinder.hpp",
    "Core/include/Acts/Utilities/GridBinFinder.ipp",
    "Core/src/EventData/SpacePointContainer2.cpp",
    "Examples/Algorithms/TrackFinding/include/ActsExamples/TrackFinding/GridTripletSeedingAlgorithm.hpp",
    "Examples/Algorithms/TrackFinding/src/GridTripletSeedingAlgorithm.cpp",
}
ALLOWED_NEW_PREFIXES = (
    "Core/include/Acts/Seeding2/",
    "Core/src/Seeding2/",
)
ALLOWED_NEW_SUFFIXES = (".cpp", ".hpp", ".ipp")


class EvaluationError(RuntimeError):
    pass


class CandidateFailure(EvaluationError):
    pass


@dataclass
class CommandResult:
    returncode: int
    output: str


def run_command(command: list[str], *, cwd: Path = PROJECT_ROOT) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout)


def git_output(*args: str) -> str:
    result = run_command(["git", "-C", str(PROJECT_ROOT), *args])
    if result.returncode != 0:
        raise EvaluationError(result.output.strip() or "git command failed")
    return result.output.strip()


def require_clean_repository() -> str:
    status = subprocess.run(
        [
            "git",
            "-C",
            str(PROJECT_ROOT),
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            ".",
            ":(exclude)Records",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if status.returncode != 0:
        raise EvaluationError(status.stdout.strip() or "could not inspect repository status")
    if status.stdout.strip():
        raise EvaluationError(
            "repository must be committed and clean before evaluation:\n" + status.stdout
        )
    return git_output("rev-parse", "HEAD")


def validate_candidate_name(candidate_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", candidate_name):
        raise EvaluationError(
            "candidate name may contain only letters, numbers, '.', '_' and '-': "
            + candidate_name
        )


def validate_optimization_files() -> list[str]:
    if not OPTIMIZATION_ROOT.is_dir():
        raise EvaluationError(f"optimization directory not found: {OPTIMIZATION_ROOT}")

    files = sorted(path for path in OPTIMIZATION_ROOT.rglob("*") if path.is_file())
    if not files:
        raise EvaluationError(f"optimization directory is empty: {OPTIMIZATION_ROOT}")

    relative_paths: list[str] = []
    for path in files:
        relative = path.relative_to(OPTIMIZATION_ROOT).as_posix()
        allowed = relative in ALLOWED_PATHS or (
            relative.startswith(ALLOWED_NEW_PREFIXES)
            and relative.endswith(ALLOWED_NEW_SUFFIXES)
        )
        if not allowed:
            raise EvaluationError(f"optimization file is outside the allowlist: {relative}")
        relative_paths.append(relative)
    return relative_paths


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_metrics(output: str) -> dict[str, Any]:
    match = re.findall(
        r"ACTS_FULL_CHAIN_ITK_METRICS\[[^]]+\] "
        r"peak_rss_kb=(\S+) user_seconds=(\S+) "
        r"system_seconds=(\S+) elapsed=(\S+)",
        output,
    )
    if not match:
        return {}
    peak_rss, user_seconds, system_seconds, elapsed = match[-1]
    return {
        "peak_rss_kb": int(peak_rss) if peak_rss.isdigit() else peak_rss,
        "user_seconds": user_seconds,
        "system_seconds": system_seconds,
        "elapsed": elapsed,
    }


def stage_completion_code(output: str) -> int | None:
    matches = re.findall(r"ACTS_FULL_CHAIN_ITK_DONE\[[^]]+\] rc=(\d+)", output)
    return int(matches[-1]) if matches else None


def helper_completion_code(output: str) -> int | None:
    matches = re.findall(r"ACTS_HELPER_RESULT\[[^]]+\] rc=(\d+)", output)
    return int(matches[-1]) if matches else None


def run_hepp_helper(helper: str, run_id: str, *arguments: str) -> CommandResult:
    return run_command([str(HEPP_HELPER), helper, run_id, *arguments])


def record_command_output(outputs: dict[str, str], name: str, result: CommandResult) -> None:
    outputs[name] = result.output


def run_stage(
    stage_results: list[dict[str, Any]],
    outputs: dict[str, str],
    *,
    name: str,
    events: int,
    stage: str,
    metrics: str,
    run_id: str,
) -> None:
    result = run_hepp_helper(
        "run-full-chain-itk.sh",
        run_id,
        str(events),
        "ttbar_pu200",
        "-1",
        "42",
        "200",
        stage,
        metrics,
        run_id,
    )
    record_command_output(outputs, name, result)
    completion_code = stage_completion_code(result.output)
    parsed_metrics = parse_metrics(result.output)
    stage_result: dict[str, Any] = {
        "name": name,
        "events": events,
        "stage": stage,
        "metrics_mode": metrics,
        "exit_code": completion_code if completion_code is not None else result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
    }
    if parsed_metrics:
        stage_result["metrics"] = parsed_metrics
    stage_results.append(stage_result)

    if result.returncode != 0:
        helper_code = helper_completion_code(result.output)
        if "helper timed out" in result.output or helper_code is None:
            raise EvaluationError(f"stage did not complete cleanly: {name}")
        raise CandidateFailure(f"candidate failed stage: {name}")


def write_summary(folder: Path, summary: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_failure_logs(folder: Path, outputs: dict[str, str]) -> None:
    logs = folder / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    for name, output in outputs.items():
        (logs / f"{name}.log").write_text(output, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_name")
    parser.add_argument(
        "--evaluation",
        action="store_true",
        help="run only the 200-event clean and timed full-chain evaluation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_candidate_name(args.candidate_name)
    relative_files = validate_optimization_files()
    commit = require_clean_repository()

    started = datetime.now(timezone.utc)
    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}-{args.candidate_name}"
    hepp_storage = os.environ.get("HEPP_STORAGE", "/storage/thomaaks")
    remote_base = f"{hepp_storage}/autoresearch-acts-evaluation/{run_id}"
    remote_optimization = f"{remote_base}/optimization-files"
    remote_run = f"{remote_base}/run"
    backup_root = f"{hepp_storage}/acts-v46.5.0-autoresearch-backup"

    outputs: dict[str, str] = {}
    stage_results: list[dict[str, Any]] = []
    category = "Errors"
    error: str | None = None
    backup_ready = False

    try:
        export_helpers = run_command(["make", "export-hepp-files"])
        record_command_output(outputs, "export_helpers", export_helpers)
        if export_helpers.returncode != 0:
            raise EvaluationError("HEPP helper export failed")

        export = run_command([str(EXPORT_OPTIMIZATION), str(OPTIMIZATION_ROOT), remote_optimization])
        record_command_output(outputs, "export_optimization", export)
        if export.returncode != 0:
            raise EvaluationError("optimization export failed")

        backup = run_hepp_helper(
            "backup-acts-files.sh",
            f"{run_id}-backup",
            remote_optimization,
            backup_root,
            remote_run,
        )
        record_command_output(outputs, "backup", backup)
        if backup.returncode != 0:
            raise EvaluationError("ACTS backup failed")
        backup_ready = True

        apply = run_hepp_helper("apply-optimization-files.sh", f"{run_id}-apply", remote_optimization)
        record_command_output(outputs, "apply", apply)
        if apply.returncode != 0:
            raise EvaluationError("optimization application failed")

        build = run_hepp_helper("build.sh", f"{run_id}-build")
        record_command_output(outputs, "build", build)
        if build.returncode != 0:
            raise EvaluationError("candidate build failed")

        if args.evaluation:
            run_stage(
                stage_results,
                outputs,
                name="two_hundred_event_full_clean",
                events=200,
                stage="full",
                metrics="none",
                run_id=f"{run_id}-200-clean",
            )
            run_stage(
                stage_results,
                outputs,
                name="two_hundred_event_full_timed",
                events=200,
                stage="full",
                metrics="time",
                run_id=f"{run_id}-200-time",
            )
            category = "Evaluation"
        else:
            run_stage(
                stage_results,
                outputs,
                name="one_event_seeding",
                events=1,
                stage="seeding",
                metrics="none",
                run_id=f"{run_id}-1-seeding",
            )
            run_stage(
                stage_results,
                outputs,
                name="one_event_full",
                events=1,
                stage="full",
                metrics="none",
                run_id=f"{run_id}-1-full",
            )
            run_stage(
                stage_results,
                outputs,
                name="fifty_event_full_clean",
                events=50,
                stage="full",
                metrics="none",
                run_id=f"{run_id}-50-clean",
            )
            run_stage(
                stage_results,
                outputs,
                name="fifty_event_full_timed",
                events=50,
                stage="full",
                metrics="time",
                run_id=f"{run_id}-50-time",
            )
            category = "Development"
    except CandidateFailure as exc:
        category = "Errors" if args.evaluation else "Failed"
        error = str(exc)
    except Exception as exc:
        category = "Errors"
        error = str(exc)
    finally:
        if backup_ready:
            restore = run_hepp_helper("restore-acts-files.sh", f"{run_id}-restore", backup_root, remote_run)
            record_command_output(outputs, "restore", restore)
            if restore.returncode != 0:
                category = "Errors"
                error = "ACTS restoration failed"
            else:
                rebuild = run_hepp_helper("build.sh", f"{run_id}-restore-build")
                record_command_output(outputs, "restore_build", rebuild)
                if rebuild.returncode != 0:
                    category = "Errors"
                    error = "pristine ACTS rebuild failed after restoration"

            cleanup = run_hepp_helper(
                "cleanup-evaluation-files.sh",
                f"{run_id}-cleanup",
                remote_optimization,
                remote_run,
            )
            record_command_output(outputs, "cleanup", cleanup)
            if cleanup.returncode != 0:
                category = "Errors"
                error = "remote evaluation cleanup failed"

    finished = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "candidate_name": args.candidate_name,
        "implementation_commit": commit,
        "mode": "evaluation" if args.evaluation else "development",
        "category": category,
        "status": "passed" if category in {"Development", "Evaluation"} else "failed",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "acts_source": "/storage/thomaaks/acts-v46.5.0",
        "acts_backup": backup_root,
        "workload": "ttbar_pu200",
        "threads": -1,
        "seed": 42,
        "pileup": 200,
        "optimization_files": relative_files,
        "stages": stage_results,
        "raw_logs_retained": category in {"Failed", "Errors"},
    }
    if error:
        summary["error"] = error

    folder = RECORDS_ROOT / category / run_id
    write_summary(folder, summary)
    if category in {"Failed", "Errors"}:
        write_failure_logs(folder, outputs)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if category in {"Development", "Evaluation"} else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvaluationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except KeyboardInterrupt:
        print("evaluation interrupted", file=sys.stderr)
        raise SystemExit(2)
