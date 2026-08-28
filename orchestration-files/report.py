#!/usr/bin/env python3
"""Build searchable ACTS result reports and interactive visualizations."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from protocol import (
    EVALUATION_TIMING_REPORTING,
    PROTOCOL_ID,
    PROTOCOL_METADATA,
    is_compatible_summary,
)
from proposal import ProposalError, median_absolute_deviation, proposal_from_summary

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = PROJECT_ROOT / "records"
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "site"
REPOSITORY_URL = "https://github.com/Aksth070600/autoresearch-acts-seeding"
FULL_COMMIT_SHA = re.compile(r"[0-9a-fA-F]{40}")

from visualizations.campaign import render as render_campaign
from visualizations.pareto import render as render_pareto

VISUALIZATIONS = {"pareto": render_pareto}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--visualization", choices=sorted(VISUALIZATIONS), default="pareto")
    parser.add_argument(
        "--dataset",
        choices=("development", "evaluation"),
        default="development",
        help="record category to include",
    )
    parser.add_argument("--baseline", default="Genesis")
    parser.add_argument("--x-metric", default="timed_seeding_time_per_event_ms")
    parser.add_argument(
        "--y-metric",
        default="timed_ambiguity_particle_efficiency",
    )
    parser.add_argument(
        "--list-metrics",
        action="store_true",
        help="print metrics found in the selected records and exit",
    )
    return parser.parse_args()


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def commit_url(commit: str) -> str:
    if not FULL_COMMIT_SHA.fullmatch(commit):
        return ""
    return f"{REPOSITORY_URL}/commit/{commit}"


def stage_prefix(stage: dict[str, Any]) -> str | None:
    name = str(stage.get("name", ""))
    if "timed" in name or stage.get("metrics_mode") == "time":
        return "timed"
    if stage.get("metrics_mode") == "none" and stage.get("events", 0) > 1:
        return "clean"
    return None


def add_metrics(metrics: dict[str, float], prefix: str, run_metrics: dict[str, Any], stage: dict[str, Any]) -> None:
    timing_total = run_metrics.get("timing_total", {})
    for source, suffix in (
        ("total_time_ms", "total_time_ms"),
        ("time_per_event_ms", "total_time_per_event_ms"),
    ):
        value = timing_total.get(source)
        if finite_number(value):
            metrics[f"{prefix}_{suffix}"] = float(value)

    timing = run_metrics.get("timing", {})
    for algorithm in ("seeding", "ckf", "ambiguity_resolution"):
        values = timing.get(algorithm, {})
        value = values.get("time_per_event_ms")
        if finite_number(value):
            metric_algorithm = "ambiguity" if algorithm == "ambiguity_resolution" else algorithm
            metrics[f"{prefix}_{metric_algorithm}_time_per_event_ms"] = float(value)

    performance = run_metrics.get("performance", {})
    algorithm_keys = {
        "ambiguity_resolution": "ambiguity",
        "seeding": "seeding",
        "ckf": "ckf",
    }
    metric_keys = {
        "efficiency_particles": "particle_efficiency",
        "efficiency_tracks": "track_efficiency",
        "fake_ratio_particles": "particle_fake_ratio",
        "fake_ratio_tracks": "track_fake_ratio",
        "duplicate_ratio_particles": "particle_duplicate_ratio",
        "duplicate_ratio_tracks": "track_duplicate_ratio",
    }
    for algorithm, values in performance.items():
        algorithm_key = algorithm_keys.get(algorithm, algorithm)
        for metric_name, value in values.items():
            if finite_number(value):
                metric_key = metric_keys.get(metric_name, metric_name)
                metrics[f"{prefix}_{algorithm_key}_{metric_key}"] = float(value)

    resource = run_metrics.get("resource_metrics", {})
    for source, suffix in (
        ("peak_rss_kb", "peak_rss_kb"),
        ("user_seconds", "user_seconds"),
        ("system_seconds", "system_seconds"),
    ):
        value = resource.get(source)
        if finite_number(value):
            metrics[f"{prefix}_{suffix}"] = float(value)

    # Keep the event count available for hover details and future comparisons.
    events = stage.get("events")
    if finite_number(events):
        metrics[f"{prefix}_events"] = float(events)


def timing_evidence(comparison: dict[str, Any]) -> dict[str, Any] | None:
    """Retain the three seeding timings and derive robust dispersion evidence."""

    repetitions = comparison.get("repetitions")
    if not isinstance(repetitions, list):
        return None
    values: list[dict[str, float | int]] = []
    for repetition in repetitions:
        if not isinstance(repetition, dict):
            return None
        value = (
            repetition.get("run_metrics", {})
            .get("timing", {})
            .get("seeding", {})
            .get("time_per_event_ms")
        )
        if not finite_number(value):
            return None
        values.append(
            {
                "repetition": int(repetition.get("repetition", len(values) + 1)),
                "time_per_event_ms": float(value),
            }
        )
    if len(values) != int(PROTOCOL_METADATA["timed_repetitions"]):
        return None
    timings = [float(item["time_per_event_ms"]) for item in values]
    return {
        "repetitions": values,
        "median_ms": float(sorted(timings)[len(timings) // 2]),
        "range_ms": max(timings) - min(timings),
        "median_absolute_deviation_ms": median_absolute_deviation(timings),
    }


def classify_speed_claim(
    candidate: dict[str, Any], genesis: dict[str, Any]
) -> dict[str, Any]:
    """Classify Evaluation speed evidence without changing scientific selection."""

    candidate_median = float(candidate["median_ms"])
    genesis_median = float(genesis["median_ms"])
    improvement = genesis_median - candidate_median
    practical_margin = max(
        float(genesis["range_ms"]),
        float(genesis["median_absolute_deviation_ms"]),
    )
    comparable_dispersion = max(
        float(candidate["median_absolute_deviation_ms"]),
        float(genesis["median_absolute_deviation_ms"]),
    )
    threshold = max(practical_margin, comparable_dispersion)
    if improvement > threshold:
        classification = "confirmed"
    elif improvement > 0:
        classification = "directional"
    else:
        classification = "inconclusive"
    return {
        "classification": classification,
        "improvement_vs_genesis_ms": improvement,
        "practical_timing_margin_ms": practical_margin,
        "comparable_dispersion_ms": comparable_dispersion,
        "confirmation_threshold_ms": threshold,
        "margin_method": EVALUATION_TIMING_REPORTING["practical_margin"],
    }


def flatten_summary(summary: dict[str, Any], path: Path, records_root: Path) -> dict[str, Any] | None:
    if summary.get("status") != "passed" or not is_compatible_summary(summary):
        return None
    stages = summary.get("stages")
    if (
        not isinstance(stages, list)
        or not stages
        or any(not isinstance(stage, dict) or stage.get("status") != "passed" for stage in stages)
    ):
        return None
    metrics: dict[str, float] = {}
    for stage in stages:
        if not isinstance(stage, dict) or stage.get("comparison") != "clean":
            continue
        if stage_prefix(stage) == "clean" and isinstance(stage.get("run_metrics"), dict):
            add_metrics(metrics, "clean", stage["run_metrics"], stage)

    timed_comparison = summary.get("timed_comparison", {})
    if not isinstance(timed_comparison, dict):
        timed_comparison = {}
    median_metrics = timed_comparison.get("median_run_metrics")
    if (
        timed_comparison.get("complete") is True
        and timed_comparison.get("aggregation") == PROTOCOL_METADATA["timed_aggregation"]
        and timed_comparison.get("repetition_count") == PROTOCOL_METADATA["timed_repetitions"]
        and isinstance(timed_comparison.get("repetitions"), list)
        and len(timed_comparison["repetitions"]) == PROTOCOL_METADATA["timed_repetitions"]
        and all(
            isinstance(repetition, dict)
            and repetition.get("status") == "passed"
            and isinstance(repetition.get("run_metrics"), dict)
            and bool(repetition.get("run_metrics"))
            for repetition in timed_comparison["repetitions"]
        )
        and isinstance(median_metrics, dict)
    ):
        timed_stage = {
            "events": timed_comparison.get("events", PROTOCOL_METADATA["development_events"]),
        }
        timed_median = dict(median_metrics)
        timed_median["resource_metrics"] = timed_comparison.get("median_resource_metrics", {})
        add_metrics(metrics, "timed", timed_median, timed_stage)

    if not metrics:
        return None
    category = str(summary.get("category", path.parent.parent.name))
    category = {"development": "Development", "evaluation": "Evaluation"}.get(
        category.lower(), category
    )
    commit = str(summary.get("implementation_commit", ""))
    try:
        measured_proposal = proposal_from_summary(summary)
    except ProposalError as error:
        raise ValueError(f"{path}: {error}") from error
    return {
        "candidate": str(summary.get("candidate_name", path.parent.name)),
        "category": category,
        "commit": commit,
        "commit_url": commit_url(commit),
        "record": path.relative_to(records_root).as_posix(),
        "protocol_id": PROTOCOL_ID,
        "metrics": metrics,
        "timing_evidence": timing_evidence(timed_comparison),
        "proposal": measured_proposal,
    }


def load_records(records_root: Path, dataset: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not records_root.is_dir():
        raise SystemExit(f"records directory not found: {records_root}")
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"warning: skipping {path}: {error}", file=sys.stderr)
            continue
        if not is_compatible_summary(summary):
            # Do not silently compare historical evidence under a new protocol.
            continue
        category = str(summary.get("category", path.parent.parent.name)).lower()
        if category != dataset:
            continue
        row = flatten_summary(summary, path, records_root)
        if row is not None:
            rows.append(row)
    return rows


def metric_label(key: str) -> str:
    labels = {
        "clean_total_time_ms": "Clean total selected time (ms)",
        "timed_total_time_ms": "Timed total selected time (ms)",
        "clean_time_per_event_ms": "Clean selected time/event (ms)",
        "timed_total_time_per_event_ms": "Diagnostic: timed full-chain time/event (ms)",
        "timed_seeding_time_per_event_ms": "PRIMARY: timed seeding time/event (ms)",
        "timed_ckf_time_per_event_ms": "Timed CKF time/event (ms)",
        "timed_ambiguity_time_per_event_ms": "Timed ambiguity time/event (ms)",
        "clean_ambiguity_particle_efficiency": "Clean ambiguity particle efficiency",
        "timed_ambiguity_particle_efficiency": "PRIMARY: timed ambiguity particle efficiency",
        "timed_peak_rss_kb": "Peak RSS (KiB)",
        "timed_user_seconds": "Timed user CPU (s)",
        "timed_system_seconds": "Timed system CPU (s)",
    }
    if key in labels:
        return labels[key]
    return key.replace("_", " ").replace("-", " ").title()


def _genesis_provenance(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "record": str(row["record"]),
            "category": str(row["category"]),
            "commit": str(row.get("commit", "")),
        }
        for row in sorted(rows, key=lambda item: str(item["record"]))
    ]


def aggregate_genesis(
    rows: list[dict[str, Any]],
    baseline: str,
    dataset: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Replace only Genesis rows with one arithmetic-mean point.

    Candidate rows stay independent. Genesis records are complete, passed,
    protocol-compatible summaries by the time they reach this function.
    """

    scoped_rows = [row for row in rows if str(row["category"]).lower() == dataset]
    genesis = [row for row in scoped_rows if row["candidate"] == baseline]
    provenance = _genesis_provenance(genesis)
    aggregation: dict[str, Any] = {
        "dataset": dataset,
        "method": "arithmetic_mean",
        "sample_count": len(genesis),
        "records": provenance,
    }
    if not genesis:
        return scoped_rows, aggregation

    common_metrics = set(genesis[0]["metrics"])
    for row in genesis[1:]:
        common_metrics.intersection_update(row["metrics"])
    if not common_metrics:
        raise ValueError("Genesis records have no common metrics to average")

    metrics = {
        key: math.fsum(float(row["metrics"][key]) for row in genesis) / len(genesis)
        for key in sorted(common_metrics)
    }
    categories = sorted({str(row["category"]) for row in genesis})
    aggregate_category = dataset.title()
    commits = {str(row.get("commit", "")) for row in genesis}
    aggregate_commit = next(iter(commits)) if len(commits) == 1 else ""
    genesis_evidence = [
        row.get("timing_evidence")
        for row in genesis
        if isinstance(row.get("timing_evidence"), dict)
    ]
    aggregate_timing_evidence = None
    if len(genesis_evidence) == len(genesis):
        aggregate_timing_evidence = {
            "repetitions": (
                list(genesis_evidence[0]["repetitions"])
                if len(genesis_evidence) == 1
                else []
            ),
            "runs": genesis_evidence,
            "median_ms": metrics.get("timed_seeding_time_per_event_ms"),
            "range_ms": max(item["range_ms"] for item in genesis_evidence),
            "median_absolute_deviation_ms": max(
                item["median_absolute_deviation_ms"] for item in genesis_evidence
            ),
        }
    aggregate = {
        "candidate": baseline,
        "category": aggregate_category,
        "commit": aggregate_commit,
        "commit_url": REPOSITORY_URL,
        "record": f"{aggregate_category}/Genesis (arithmetic mean)",
        "protocol_id": PROTOCOL_ID,
        "metrics": metrics,
        "sample_count": len(genesis),
        "provenance": provenance,
        "source_categories": categories,
        "timing_evidence": aggregate_timing_evidence,
        "proposal": None,
    }
    return [aggregate, *[row for row in scoped_rows if row["candidate"] != baseline]], aggregation


def build_report(
    rows: list[dict[str, Any]],
    baseline: str,
    dataset: str = "development",
) -> dict[str, Any]:
    report_rows, genesis_aggregation = aggregate_genesis(rows, baseline, dataset)
    if dataset == "evaluation":
        genesis = next(
            (row for row in report_rows if row["candidate"] == baseline), None
        )
        genesis_evidence = genesis.get("timing_evidence") if genesis else None
        for row in report_rows:
            evidence = row.get("timing_evidence")
            row["speed_claim"] = (
                classify_speed_claim(evidence, genesis_evidence)
                if row["candidate"] != baseline
                and isinstance(evidence, dict)
                and isinstance(genesis_evidence, dict)
                else None
            )
    metric_keys = sorted({key for row in report_rows for key in row["metrics"]})
    return {
        "rows": report_rows,
        "metric_keys": metric_keys,
        "metric_labels": {key: metric_label(key) for key in metric_keys},
        "baseline": baseline,
        "dataset": dataset,
        "genesis_aggregation": genesis_aggregation,
        "protocol_id": PROTOCOL_ID,
        "repository_url": REPOSITORY_URL,
        "protocol": PROTOCOL_METADATA,
        "primary_objectives": {
            "minimize": "timed_seeding_time_per_event_ms",
            "maximize": "timed_ambiguity_particle_efficiency",
        },
        "evaluation_timing_policy": {
            **EVALUATION_TIMING_REPORTING,
            "scope": "reporting and captain selection evidence only",
        },
    }


def main() -> int:
    args = parse_args()
    records_root = args.records.resolve()
    output_root = args.output.resolve()
    rows = load_records(records_root, args.dataset)
    report = build_report(rows, args.baseline, args.dataset)

    if args.list_metrics:
        for key in report["metric_keys"]:
            print(f"{key}\t{report['metric_labels'][key]}")
        return 0

    # A freshly reset campaign has no summaries and should still produce a
    # reviewable placeholder. If summaries exist, retain strict metric checks
    # so malformed or incomplete Genesis records do not pass unnoticed.
    summary_paths = list(records_root.glob(f"{args.dataset.title()}/**/summary.json"))
    if rows or summary_paths:
        if args.x_metric not in report["metric_keys"]:
            raise SystemExit(f"x metric not found: {args.x_metric}")
        if args.y_metric not in report["metric_keys"]:
            raise SystemExit(f"y metric not found: {args.y_metric}")
        for row in rows:
            if args.x_metric not in row["metrics"] or args.y_metric not in row["metrics"]:
                raise SystemExit(
                    "malformed populated record: missing selected report metrics in "
                    + str(row["record"])
                )
        for path in summary_paths:
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                is_compatible_summary(summary)
                and summary.get("status") == "passed"
                and flatten_summary(summary, path, records_root) is None
            ):
                raise SystemExit(f"malformed populated record: {path}")

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / ".nojekyll").write_text("", encoding="utf-8")
    index = output_root / "index.html"
    VISUALIZATIONS[args.visualization](
        report,
        index,
        defaults={
            "x_metric": args.x_metric,
            "y_metric": args.y_metric,
            "baseline": args.baseline,
        },
    )
    campaign_index = output_root / "campaign" / "index.html"
    render_campaign(campaign_index)
    print(f"wrote {index}")
    print(f"wrote {campaign_index}")
    print(f"included {len(rows)} passed record(s) from {args.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
