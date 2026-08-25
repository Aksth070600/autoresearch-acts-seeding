#!/usr/bin/env python3
"""Build searchable ACTS result reports and interactive visualizations."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = PROJECT_ROOT / "Records"
DEFAULT_OUTPUT = PROJECT_ROOT / "reports" / "site"

from visualizations.pareto import render as render_pareto

VISUALIZATIONS = {"pareto": render_pareto}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--visualization", choices=sorted(VISUALIZATIONS), default="pareto")
    parser.add_argument(
        "--dataset",
        choices=("development", "evaluation", "all"),
        default="development",
        help="record category to include",
    )
    parser.add_argument("--baseline", default="baseline")
    parser.add_argument("--x-metric", default="timed_total_time_ms")
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
        ("time_per_event_ms", "time_per_event_ms"),
    ):
        value = timing_total.get(source)
        if finite_number(value):
            metrics[f"{prefix}_{suffix}"] = float(value)

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


def flatten_summary(summary: dict[str, Any], path: Path, records_root: Path) -> dict[str, Any] | None:
    if summary.get("status") != "passed":
        return None
    metrics: dict[str, float] = {}
    for stage in summary.get("stages", []):
        if not isinstance(stage, dict):
            continue
        prefix = stage_prefix(stage)
        run_metrics = stage.get("run_metrics")
        if prefix is not None and isinstance(run_metrics, dict):
            add_metrics(metrics, prefix, run_metrics, stage)

    if not metrics:
        return None
    category = str(summary.get("category", path.parent.parent.name))
    return {
        "candidate": str(summary.get("candidate_name", path.parent.name)),
        "category": category,
        "commit": str(summary.get("implementation_commit", "")),
        "record": path.relative_to(records_root).as_posix(),
        "metrics": metrics,
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
        category = str(summary.get("category", path.parent.parent.name)).lower()
        if dataset != "all" and category != dataset:
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
        "timed_time_per_event_ms": "Timed selected time/event (ms)",
        "clean_ambiguity_particle_efficiency": "Clean ambiguity particle efficiency",
        "timed_ambiguity_particle_efficiency": "Timed ambiguity particle efficiency",
        "timed_peak_rss_kb": "Timed peak RSS (kB)",
        "timed_user_seconds": "Timed user CPU (s)",
        "timed_system_seconds": "Timed system CPU (s)",
    }
    if key in labels:
        return labels[key]
    return key.replace("_", " ").replace("-", " ").title()


def build_report(rows: list[dict[str, Any]], baseline: str) -> dict[str, Any]:
    metric_keys = sorted({key for row in rows for key in row["metrics"]})
    return {
        "rows": rows,
        "metric_keys": metric_keys,
        "metric_labels": {key: metric_label(key) for key in metric_keys},
        "baseline": baseline,
    }


def main() -> int:
    args = parse_args()
    records_root = args.records.resolve()
    output_root = args.output.resolve()
    rows = load_records(records_root, args.dataset)
    report = build_report(rows, args.baseline)

    if args.list_metrics:
        for key in report["metric_keys"]:
            print(f"{key}\t{report['metric_labels'][key]}")
        return 0

    if args.x_metric not in report["metric_keys"]:
        raise SystemExit(f"x metric not found: {args.x_metric}")
    if args.y_metric not in report["metric_keys"]:
        raise SystemExit(f"y metric not found: {args.y_metric}")

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
    print(f"wrote {index}")
    print(f"included {len(rows)} passed record(s) from {args.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
