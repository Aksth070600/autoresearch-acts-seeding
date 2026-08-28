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
from statistics import median
from typing import Any

from protocol import PROTOCOL_ID, PROTOCOL_METADATA, current_protocol, protocol_events
from proposal import ProposalError, bind_proposal, median_absolute_deviation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPTIMIZATION_ROOT = PROJECT_ROOT / "optimization-files"
RECORDS_ROOT = PROJECT_ROOT / "records"
HEPP_HELPER = PROJECT_ROOT / "orchestration-files" / "HEPP-files" / "run-hepp-helper.sh"
EXPORT_OPTIMIZATION = PROJECT_ROOT / "orchestration-files" / "HEPP-files" / "export-optimization-files.sh"
DEFAULT_CAMPAIGN_INPUT = PROJECT_ROOT / "orchestration-files" / "campaign-status-input.json"

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
            ":(exclude)records",
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


def candidate_implementation_commit(
    candidate_name: str, repository_commit: str
) -> str:
    if candidate_name == "Genesis":
        return repository_commit
    commit = git_output(
        "rev-list",
        "-1",
        repository_commit,
        "--",
        "optimization-files",
    ).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise EvaluationError(
            "could not determine the candidate optimization-files commit"
        )
    return commit


def candidate_implementation_files(implementation_commit: str) -> list[str]:
    output = git_output(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        implementation_commit,
        "--",
        "optimization-files",
    )
    return sorted(line for line in output.splitlines() if line)


def load_candidate_proposal(
    campaign_input: Path,
    candidate_name: str,
    implementation_commit: str,
    implementation_files: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and bind the committed campaign proposal before scientific work."""

    try:
        state = json.loads(campaign_input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"cannot read candidate proposal metadata: {error}") from error
    metadata = state.get("attempt_metadata") if isinstance(state, dict) else None
    if not isinstance(metadata, list):
        raise EvaluationError("campaign input has no attempt_metadata array")
    matches = [
        item
        for item in metadata
        if isinstance(item, dict) and item.get("candidate") == candidate_name
    ]
    if len(matches) != 1:
        raise EvaluationError(
            "candidate must have exactly one pre-run proposal in campaign input"
        )
    item = matches[0]
    if "proposal" not in item:
        raise EvaluationError("non-Genesis candidate proposal is required before evaluation")
    try:
        binding = bind_proposal(
            item["proposal"],
            candidate_name,
            implementation_commit,
            implementation_files,
        )
    except ProposalError as error:
        raise EvaluationError(str(error)) from error
    proposal_provenance = binding["proposal"]["combination_provenance"]
    metadata_provenance = item.get("combination_provenance")
    if (item.get("classification") == "combination") != (proposal_provenance is not None):
        raise EvaluationError("candidate classification and combination provenance disagree")
    if metadata_provenance != proposal_provenance:
        raise EvaluationError(
            "candidate combination provenance does not match the bound proposal"
        )
    identity = {
        "mechanism_key": item.get("mechanism_key"),
        "mechanism_family": item.get("mechanism_family"),
        "classification": item.get("classification"),
        "derives_from": item.get("derives_from"),
    }
    if not all(
        isinstance(identity[name], str) and identity[name]
        for name in ("mechanism_key", "mechanism_family", "classification")
    ):
        raise EvaluationError("candidate identity metadata is incomplete")
    return binding, identity


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


def parse_run_metrics(output: str) -> dict[str, Any]:
    metric_pattern = re.compile(
        r"RootTrackFin\s+INFO\s+(.+?) = "
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)$"
    )
    metric_names = {
        "Efficiency with tracks (nMatchedTracks/ nAllTracks)": "efficiency_tracks",
        "Fake ratio with tracks (nFakeTracks/nAllTracks)": "fake_ratio_tracks",
        "Duplicate ratio with tracks (nDuplicateTracks/nAllTracks)": "duplicate_ratio_tracks",
        "Efficiency with particles (nMatchedParticles/nTrueParticles)": "efficiency_particles",
        "Fake ratio with particles (nFakeParticles/nTrueParticles)": "fake_ratio_particles",
        "Duplicate ratio with particles (nDuplicateParticles/nTrueParticles)": "duplicate_ratio_particles",
    }
    performance: dict[str, dict[str, float]] = {}
    pending_performance: dict[str, float] = {}
    track_finding: dict[str, int | float] = {}
    timing: dict[str, dict[str, float]] = {}
    stat_names = {
        "total seeds": "total_seeds",
        "deduplicated seeds": "deduplicated_seeds",
        "failed seeds": "failed_seeds",
        "failed smoothing": "failed_smoothing",
        "failed extrapolation": "failed_extrapolation",
        "failure ratio seeds": "failure_ratio_seeds",
        "found tracks": "found_tracks",
        "selected tracks": "selected_tracks",
        "stopped branches": "stopped_branches",
        "skipped second pass": "skipped_second_pass",
    }
    timing_names = {
        "GridTripletSeedingAlgorithm": "seeding",
        "TrackFindingAlgorithm": "ckf",
        "GreedyAmbiguityResolutionAlgorithm": "ambiguity_resolution",
    }

    for raw_line in output.splitlines():
        line = raw_line.strip()
        metric_match = metric_pattern.search(line)
        if metric_match and metric_match.group(1) in metric_names:
            pending_performance[metric_names[metric_match.group(1)]] = float(metric_match.group(2))

        performance_match = re.search(r"performance_(seeding|finding_ckf|finding_ambi)\.root", line)
        if performance_match and pending_performance:
            tag_to_name = {
                "seeding": "seeding",
                "finding_ckf": "ckf",
                "finding_ambi": "ambiguity_resolution",
            }
            performance[tag_to_name[performance_match.group(1)]] = pending_performance
            pending_performance = {}

        for raw_name, name in stat_names.items():
            stat_match = re.search(rf"- {re.escape(raw_name)}: ([0-9]+(?:\.[0-9]+)?)", line)
            if stat_match:
                value = float(stat_match.group(1))
                track_finding[name] = int(value) if value.is_integer() else value

        timing_match = re.search(
            r"\| Algorithm:(GridTripletSeedingAlgorithm|TrackFindingAlgorithm|"
            r"GreedyAmbiguityResolutionAlgorithm)\s*\|\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s*\|\s*"
            r"([0-9]+(?:\.[0-9]+)?)\s*\|\s*"
            r"([0-9]+(?:\.[0-9]+)?)%\s*\|",
            line,
        )
        if timing_match:
            name = timing_names[timing_match.group(1)]
            timing[name] = {
                "total_time_ms": float(timing_match.group(2)),
                "time_per_event_ms": float(timing_match.group(3)),
            }

    metrics: dict[str, Any] = {}
    if performance:
        metrics["performance"] = performance
    if track_finding:
        metrics["ckf_statistics"] = track_finding
    if timing:
        metrics["timing"] = timing
        required_timing = ("seeding", "ckf", "ambiguity_resolution")
        if all(name in timing for name in required_timing):
            total_time_ms = sum(timing[name]["total_time_ms"] for name in required_timing)
            total_time_per_event_ms = sum(
                timing[name]["time_per_event_ms"] for name in required_timing
            )
            for name in required_timing:
                timing[name]["fraction_percent"] = round(
                    100.0 * timing[name]["total_time_ms"] / total_time_ms,
                    6,
                )
            metrics["timing_total"] = {
                "total_time_ms": total_time_ms,
                "time_per_event_ms": total_time_per_event_ms,
                "fraction_percent": 100.0,
            }
    return metrics


def stage_completion_code(output: str) -> int | None:
    matches = re.findall(r"ACTS_FULL_CHAIN_ITK_DONE\[[^]]+\] rc=(\d+)", output)
    return int(matches[-1]) if matches else None


def helper_completion_code(output: str) -> int | None:
    matches = re.findall(r"ACTS_HELPER_RESULT\[[^]]+\] rc=(\d+)", output)
    return int(matches[-1]) if matches else None


def expected_fpe_completion(output: str, events: int) -> dict[str, int] | None:
    fpe_matches = re.findall(r"Encountered (\d+) unmasked FPEs", output)
    processed_matches = re.findall(r"Processed (\d+) events in", output)
    if not fpe_matches or not processed_matches:
        return None
    processed_events = int(processed_matches[-1])
    if processed_events != events:
        return None
    return {
        "unmasked_fpes": int(fpe_matches[-1]),
        "processed_events": processed_events,
    }


def run_hepp_helper(helper: str, run_id: str, *arguments: str) -> CommandResult:
    return run_command([str(HEPP_HELPER), helper, run_id, *arguments])


def record_command_output(outputs: dict[str, str], name: str, result: CommandResult) -> None:
    outputs[name] = result.output


def require_capped_build_log(result: CommandResult) -> None:
    """Reject a build whose log does not confirm the campaign resource cap."""

    build_jobs = os.environ.get("ACTS_BUILD_JOBS")
    if build_jobs != "8":
        raise EvaluationError(
            f"ACTS_BUILD_JOBS must be explicitly set to 8, got {build_jobs!r}"
        )
    if "ACTS build parallel jobs: 8" not in result.output:
        raise EvaluationError("candidate build log did not confirm the eight-job cap")


def run_stage(
    stage_results: list[dict[str, Any]],
    outputs: dict[str, str],
    *,
    name: str,
    events: int,
    stage: str,
    metrics: str,
    run_id: str,
    comparison: str | None = None,
    repetition: int | None = None,
) -> None:
    result = run_hepp_helper(
        "run-full-chain-itk.sh",
        run_id,
        str(events),
        str(PROTOCOL_METADATA["dataset"]),
        str(PROTOCOL_METADATA["threads"]),
        str(PROTOCOL_METADATA["seed"]),
        str(PROTOCOL_METADATA["pileup"]),
        stage,
        metrics,
        run_id,
    )
    record_command_output(outputs, name, result)
    completion_code = stage_completion_code(result.output)
    parsed_metrics = parse_metrics(result.output)
    parsed_run_metrics = parse_run_metrics(result.output)
    expected_fpes = expected_fpe_completion(result.output, events)
    accepted_expected_fpes = result.returncode != 0 and expected_fpes is not None
    raw_exit_code = completion_code if completion_code is not None else result.returncode
    stage_passed = result.returncode == 0 or accepted_expected_fpes
    stage_result: dict[str, Any] = {
        "name": name,
        "events": events,
        "stage": stage,
        "metrics_mode": metrics,
        "protocol_id": PROTOCOL_ID,
        "exit_code": 0 if stage_passed else raw_exit_code,
        "status": "passed" if stage_passed else "failed",
    }
    if comparison is not None:
        stage_result["comparison"] = comparison
    if repetition is not None:
        stage_result["repetition"] = repetition
    if raw_exit_code != 0:
        stage_result["raw_exit_code"] = raw_exit_code
    if expected_fpes is not None:
        stage_result["expected_nonfatal"] = expected_fpes
    if parsed_run_metrics:
        stage_result["run_metrics"] = parsed_run_metrics
    if parsed_metrics:
        stage_result["resource_metrics"] = parsed_metrics
    stage_results.append(stage_result)

    if not stage_passed:
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


def median_numeric_tree(values: list[Any]) -> Any:
    """Take a per-leaf median while preserving the parsed metric structure."""

    if not values:
        return {}
    if all(isinstance(value, dict) for value in values):
        common_keys = set(values[0])
        for value in values[1:]:
            common_keys.intersection_update(value)
        result: dict[str, Any] = {}
        for key in sorted(common_keys):
            median_value = median_numeric_tree([value[key] for value in values])
            if median_value is not None and median_value != {}:
                result[key] = median_value
        return result
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        return median(values)
    return None


def dispersion_numeric_tree(values: list[Any], statistic: str) -> Any:
    """Calculate per-leaf range or unscaled MAD for repeated metrics."""

    if not values:
        return {}
    if all(isinstance(value, dict) for value in values):
        common_keys = set(values[0])
        for value in values[1:]:
            common_keys.intersection_update(value)
        result: dict[str, Any] = {}
        for key in sorted(common_keys):
            dispersion = dispersion_numeric_tree([value[key] for value in values], statistic)
            if dispersion is not None and dispersion != {}:
                result[key] = dispersion
        return result
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        numeric = [float(value) for value in values]
        if statistic == "range":
            return max(numeric) - min(numeric)
        if statistic == "median_absolute_deviation":
            return median_absolute_deviation(numeric)
        raise ValueError(f"unsupported dispersion statistic: {statistic}")
    return None


def build_rss_evidence(stage_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the separate instrumented RSS run without timing aggregation."""

    stages = [stage for stage in stage_results if stage.get("comparison") == "rss"]
    if not stages:
        return None
    if len(stages) != 1:
        return {"complete": False, "run_count": len(stages)}
    stage = stages[0]
    resource_metrics = stage.get("resource_metrics", {})
    complete = (
        stage.get("status") == "passed"
        and stage.get("stage") == PROTOCOL_METADATA["execution_stage"]
        and stage.get("metrics_mode") == PROTOCOL_METADATA["rss_metrics_mode"]
        and stage.get("events") == PROTOCOL_METADATA["rss_events"]
        and isinstance(resource_metrics, dict)
        and isinstance(resource_metrics.get("peak_rss_kb"), (int, float))
        and not isinstance(resource_metrics.get("peak_rss_kb"), bool)
        and resource_metrics["peak_rss_kb"] >= 0
    )
    return {
        "complete": complete,
        "events": stage.get("events"),
        "stage": stage.get("stage"),
        "metrics_mode": stage.get("metrics_mode"),
        "status": stage.get("status"),
        "resource_metrics": resource_metrics,
    }


def build_timed_comparison(stage_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Summarize timed repetitions without discarding their individual evidence."""

    timed = [stage for stage in stage_results if stage.get("comparison") == "timed"]
    if not timed:
        return None
    repetitions = [
        {
            "repetition": stage.get("repetition"),
            "name": stage.get("name"),
            "events": stage.get("events"),
            "stage": stage.get("stage"),
            "metrics_mode": stage.get("metrics_mode"),
            "status": stage.get("status"),
            "exit_code": stage.get("exit_code"),
            "expected_nonfatal": stage.get("expected_nonfatal"),
            "run_metrics": stage.get("run_metrics", {}),
            "resource_metrics": stage.get("resource_metrics", {}),
        }
        for stage in timed
    ]
    complete = len(timed) == int(PROTOCOL_METADATA["timed_repetitions"]) and all(
        stage.get("status") == "passed"
        and stage.get("stage") == PROTOCOL_METADATA["execution_stage"]
        and stage.get("metrics_mode") == PROTOCOL_METADATA["timing_instrumentation"]
        and stage.get("events") == PROTOCOL_METADATA["timing_events"]
        and not stage.get("resource_metrics")
        and isinstance(stage.get("run_metrics"), dict)
        and bool(stage.get("run_metrics"))
        for stage in timed
    )
    comparison: dict[str, Any] = {
        "aggregation": PROTOCOL_METADATA["timed_aggregation"],
        "repetition_count": len(repetitions),
        "required_repetitions": PROTOCOL_METADATA["timed_repetitions"],
        "events": timed[0].get("events"),
        "complete": complete,
        "repetitions": repetitions,
    }
    if complete:
        run_metrics = [stage["run_metrics"] for stage in timed]
        comparison["median_run_metrics"] = median_numeric_tree(run_metrics)
        comparison["range_run_metrics"] = dispersion_numeric_tree(
            run_metrics, "range"
        )
        comparison["median_absolute_deviation_run_metrics"] = dispersion_numeric_tree(
            run_metrics, "median_absolute_deviation"
        )
    return comparison


def controlled_stage_plan() -> list[dict[str, Any]]:
    """Return the exact seeding-only 1 + 3 + 1 stage matrix for either mode."""

    plan = [
        {
            "name": "one_event_seeding_smoke",
            "events": protocol_events("smoke"),
            "stage": "seeding",
            "metrics": PROTOCOL_METADATA["smoke_instrumentation"],
            "comparison": "smoke",
        }
    ]
    plan.extend(
        {
            "name": f"ten_event_seeding_timing_repetition_{repetition}",
            "events": protocol_events("timing"),
            "stage": "seeding",
            "metrics": PROTOCOL_METADATA["timing_instrumentation"],
            "comparison": "timed",
            "repetition": repetition,
        }
        for repetition in range(1, int(PROTOCOL_METADATA["timed_repetitions"]) + 1)
    )
    plan.append(
        {
            "name": "ten_event_seeding_rss",
            "events": protocol_events("rss"),
            "stage": "seeding",
            "metrics": PROTOCOL_METADATA["rss_metrics_mode"],
            "comparison": "rss",
        }
    )
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_name")
    parser.add_argument(
        "--evaluation",
        action="store_true",
        help="write captain-authorized Evaluation records using the seeding-only matrix",
    )
    parser.add_argument(
        "--campaign-input",
        type=Path,
        default=DEFAULT_CAMPAIGN_INPUT,
        help="pre-run candidate proposal metadata",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_candidate_name(args.candidate_name)
    relative_files = validate_optimization_files()
    repository_commit = require_clean_repository()
    commit = candidate_implementation_commit(
        args.candidate_name, repository_commit
    )
    proposal_binding = None
    candidate_identity = None
    if args.candidate_name != "Genesis":
        proposal_binding, candidate_identity = load_candidate_proposal(
            args.campaign_input,
            args.candidate_name,
            commit,
            candidate_implementation_files(commit),
        )

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
        require_capped_build_log(build)

        for planned in controlled_stage_plan():
            stage_run_id = (
                f"{run_id}-{planned['events']}-{planned['comparison']}"
                + (
                    f"-r{planned['repetition']}"
                    if "repetition" in planned
                    else ""
                )
            )
            run_stage(
                stage_results,
                outputs,
                name=planned["name"],
                events=planned["events"],
                stage=planned["stage"],
                metrics=planned["metrics"],
                run_id=stage_run_id,
                comparison=planned["comparison"],
                repetition=planned.get("repetition"),
            )
        category = "Evaluation" if args.evaluation else "Development"
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
                else:
                    try:
                        require_capped_build_log(rebuild)
                    except EvaluationError as exc:
                        category = "Errors"
                        error = str(exc)

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

    timed_comparison = build_timed_comparison(stage_results)
    rss_evidence = build_rss_evidence(stage_results)
    if category in {"Development", "Evaluation"} and (
        timed_comparison is None or not timed_comparison.get("complete")
    ):
        category = "Errors"
        error = error or "timed repetitions did not produce a complete median"
    if category in {"Development", "Evaluation"} and (
        rss_evidence is None or not rss_evidence.get("complete")
    ):
        category = "Errors"
        error = error or "separate RSS run did not produce complete evidence"

    finished = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "candidate_name": args.candidate_name,
        "protocol_id": PROTOCOL_ID,
        "protocol": current_protocol(),
        "execution_target": PROTOCOL_METADATA["execution_target"],
        "timed_repetitions": PROTOCOL_METADATA["timed_repetitions"],
        "timed_aggregation": PROTOCOL_METADATA["timed_aggregation"],
        "baseline": args.candidate_name == "Genesis" and category in {"Development", "Evaluation"},
        "implementation_commit": commit,
        "mode": "evaluation" if args.evaluation else "development",
        "category": category,
        "status": "passed" if category in {"Development", "Evaluation"} else "failed",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "acts_source": "/storage/thomaaks/acts-v46.5.0",
        "acts_backup": backup_root,
        "workload": "ttbar_pu200",
        "threads": PROTOCOL_METADATA["threads"],
        "seed": PROTOCOL_METADATA["seed"],
        "pileup": PROTOCOL_METADATA["pileup"],
        "build_parallel_jobs": int(os.environ.get("ACTS_BUILD_JOBS", "0")),
        "optimization_files": relative_files,
        "stages": stage_results,
        "timed_comparison": timed_comparison,
        "rss_evidence": rss_evidence,
        "raw_logs_retained": category in {"Failed", "Errors"},
    }
    if error:
        summary["error"] = error
    if proposal_binding is not None and candidate_identity is not None:
        summary["proposal_binding"] = proposal_binding
        summary["combination_provenance"] = proposal_binding["proposal"][
            "combination_provenance"
        ]
        summary["candidate_identity"] = candidate_identity

    if args.candidate_name == "Genesis" and category in {"Development", "Evaluation"}:
        # Keep every successful Genesis run. The timestamp is part of the
        # directory name so each campaign has a durable baseline record.
        timestamp = started.strftime("%Y%m%dT%H%M%S%fZ")
        record_name = f"{timestamp}-Genesis"
        suffix = 2
        while (RECORDS_ROOT / category / record_name).exists():
            record_name = f"{timestamp}-{suffix}-Genesis"
            suffix += 1
    else:
        record_name = run_id
    folder = RECORDS_ROOT / category / record_name
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
