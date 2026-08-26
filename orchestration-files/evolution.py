#!/usr/bin/env python3
"""Select promising ACTS candidates with a historical NSGA-II population."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol import PROTOCOL_ID, PROTOCOL_METADATA, is_compatible_summary

try:
    import numpy as np
    from pymoo.algorithms.moo.nsga2 import NSGA2
    from pymoo.core.problem import ElementwiseProblem
    from pymoo.optimize import minimize
    from pymoo.operators.crossover.sbx import SBX
    from pymoo.operators.mutation.pm import PM
    from pymoo.operators.sampling.rnd import IntegerRandomSampling
except ImportError as error:  # pragma: no cover - exercised by the CLI environment
    raise SystemExit(
        "evolution.py requires pymoo. Install the pinned dependencies with "
        "python3 -m pip install -r orchestration-files/requirements.txt"
    ) from error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = PROJECT_ROOT / "records"
DEFAULT_STATE = DEFAULT_RECORDS / "evolution" / "population.json"

PRIMARY_TIME_METRIC = "total_time_per_event_ms"
PRIMARY_EFFICIENCY_METRIC = "ambiguity_particle_efficiency"
PRIMARY_METRICS = (PRIMARY_TIME_METRIC, PRIMARY_EFFICIENCY_METRIC)
DIAGNOSTIC_METRICS = (
    "seeding_time_per_event_ms",
    "seeding_particle_efficiency",
    "ckf_particle_efficiency",
    "ambiguity_track_efficiency",
)
ALGORITHMS = ("seeding", "ckf", "ambiguity")


class EvolutionError(RuntimeError):
    """Raised when the historical candidate pool cannot be evaluated."""


class HistoricalCandidateProblem(ElementwiseProblem):
    """Discrete NSGA-II problem whose decision variable indexes known records."""

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        super().__init__(
            n_var=1,
            n_obj=2,
            n_ieq_constr=0,
            xl=0,
            xu=max(0, len(candidates) - 1),
            vtype=int,
        )

    def _evaluate(self, x: np.ndarray, out: dict[str, Any], **kwargs: Any) -> None:
        index = min(max(int(round(float(x[0]))), 0), len(self.candidates) - 1)
        out["F"] = self.candidates[index]["objectives"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--dataset", choices=("development", "evaluation", "all"), default="development")
    parser.add_argument("--baseline", default="Genesis")
    parser.add_argument("--stage", choices=("clean", "timed"), default="timed")
    parser.add_argument(
        "--efficiency-kind",
        choices=("particles",),
        default="particles",
        help="compatibility option; the objective is always particle ambiguity efficiency",
    )
    parser.add_argument("--population-size", type=int, default=10)
    parser.add_argument("--generations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", action="store_true", help="emit the recommendation as JSON")
    return parser.parse_args()


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def stage_prefix(stage: dict[str, Any]) -> str | None:
    name = str(stage.get("name", ""))
    if "timed" in name or stage.get("metrics_mode") == "time":
        return "timed"
    if stage.get("metrics_mode") == "none" and stage.get("events", 0) > 1:
        return "clean"
    return None


def add_run_metrics(metrics: dict[str, float], prefix: str, run_metrics: dict[str, Any]) -> None:
    """Flatten primary and diagnostic values from one parsed full-chain run."""

    timing = run_metrics.get("timing", {})
    timing_total = run_metrics.get("timing_total", {})
    for source, name in (
        (timing_total.get("time_per_event_ms"), "total_time_per_event_ms"),
        (timing.get("seeding", {}).get("time_per_event_ms"), "seeding_time_per_event_ms"),
    ):
        if finite(source):
            metrics[f"{prefix}_{name}"] = float(source)

    performance = run_metrics.get("performance", {})
    for algorithm in ALGORITHMS:
        source_name = "ambiguity_resolution" if algorithm == "ambiguity" else algorithm
        values = performance.get(source_name, {})
        for metric_name, value in values.items():
            if finite(value):
                normalized = {
                    "efficiency_particles": "particle_efficiency",
                    "efficiency_tracks": "track_efficiency",
                    "fake_ratio_particles": "particle_fake_ratio",
                    "fake_ratio_tracks": "track_fake_ratio",
                    "duplicate_ratio_particles": "particle_duplicate_ratio",
                    "duplicate_ratio_tracks": "track_duplicate_ratio",
                }.get(metric_name, metric_name)
                metrics[f"{prefix}_{algorithm}_{normalized}"] = float(value)


def flatten_summary(
    summary: dict[str, Any],
    path: Path,
    records_root: Path,
    efficiency_kind: str,
) -> dict[str, Any] | None:
    del efficiency_kind  # The campaign objective is always particle ambiguity efficiency.
    if summary.get("status") != "passed" or not is_compatible_summary(summary):
        return None
    metrics: dict[str, float] = {}
    for stage in summary.get("stages", []):
        if not isinstance(stage, dict) or stage.get("comparison") != "clean":
            continue
        if stage_prefix(stage) == "clean" and isinstance(stage.get("run_metrics"), dict):
            add_run_metrics(metrics, "clean", stage["run_metrics"])

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
        and isinstance(median_metrics, dict)
    ):
        add_run_metrics(metrics, "timed", median_metrics)

    required = {f"timed_{name}" for name in PRIMARY_METRICS}
    if not required.issubset(metrics):
        return None
    return {
        "candidate": str(summary.get("candidate_name", path.parent.name)),
        "category": str(summary.get("category", path.parent.parent.name)),
        "commit": str(summary.get("implementation_commit", "")),
        "record": path.relative_to(records_root).as_posix(),
        "protocol_id": PROTOCOL_ID,
        "is_baseline": bool(summary.get("baseline")),
        "metrics": metrics,
    }


def load_records(records_root: Path, dataset: str, efficiency_kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not is_compatible_summary(summary):
            # Old evidence is deliberately not compared under this protocol.
            continue
        category = str(summary.get("category", path.parent.parent.name)).lower()
        if dataset != "all" and category != dataset:
            continue
        row = flatten_summary(summary, path, records_root, efficiency_kind)
        if row is not None:
            rows.append(row)
    return rows


def choose_baseline(rows: list[dict[str, Any]], candidate_name: str) -> dict[str, Any]:
    """Require the canonical fresh Genesis record for the active protocol."""

    matches = [row for row in rows if row["candidate"] == candidate_name]
    fresh = [
        row
        for row in matches
        if row["category"].lower() == "development"
        and row["record"] == "Development/Genesis/summary.json"
    ]
    if not fresh:
        raise EvolutionError(
            "fresh protocol-compatible Development/Genesis baseline required; "
            "run `make evaluate CANDIDATE=Genesis` first"
        )
    return fresh[0]


def required_metrics(stage: str) -> tuple[str, ...]:
    return tuple(f"{stage}_{name}" for name in PRIMARY_METRICS)


def improved_over_baseline(row: dict[str, Any], baseline: dict[str, Any], stage: str) -> bool:
    metrics = row["metrics"]
    base = baseline["metrics"]
    if any(name not in metrics or name not in base for name in required_metrics(stage)):
        return False
    time_improved = metrics[f"{stage}_{PRIMARY_TIME_METRIC}"] < base[f"{stage}_{PRIMARY_TIME_METRIC}"]
    ambiguity_improved = (
        metrics[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
        > base[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
    )
    return time_improved or ambiguity_improved


def objective_vector(row: dict[str, Any], stage: str) -> list[float]:
    """Return the two primary objectives: time down, ambiguity efficiency up."""

    metrics = row["metrics"]
    return [
        metrics[f"{stage}_{PRIMARY_TIME_METRIC}"],
        -metrics[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"],
    ]


def dominates(left: dict[str, Any], right: dict[str, Any], stage: str) -> bool:
    """Return whether left is at least as good on both primary objectives."""

    left_metrics = left["metrics"]
    right_metrics = right["metrics"]
    left_time = left_metrics[f"{stage}_{PRIMARY_TIME_METRIC}"]
    right_time = right_metrics[f"{stage}_{PRIMARY_TIME_METRIC}"]
    left_efficiency = left_metrics[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
    right_efficiency = right_metrics[f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"]
    return (
        left_time <= right_time
        and left_efficiency >= right_efficiency
        and (left_time < right_time or left_efficiency > right_efficiency)
    )


def pareto_front(rows: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    """Keep candidates not dominated on either primary metric."""

    return [
        row
        for row in rows
        if not any(other is not row and dominates(other, row, stage) for other in rows)
    ]


def candidate_pool(rows: list[dict[str, Any]], baseline: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    pool = [row for row in rows if improved_over_baseline(row, baseline, stage)]
    pool = [row for row in pool if row["record"] != baseline["record"]]
    baseline_copy = dict(baseline)
    baseline_copy["is_baseline"] = True
    pool.insert(0, baseline_copy)
    unique: dict[str, dict[str, Any]] = {}
    for row in pool:
        row["objectives"] = objective_vector(row, stage)
        unique[row["record"]] = row
    return list(unique.values())


def select_population(pool: list[dict[str, Any]], size: int, generations: int, seed: int) -> list[dict[str, Any]]:
    if len(pool) <= size:
        return pool
    problem = HistoricalCandidateProblem(pool)
    algorithm = NSGA2(
        pop_size=min(size, len(pool)),
        sampling=IntegerRandomSampling(),
        crossover=SBX(prob=0.9, eta=15, vtype=int),
        mutation=PM(prob=0.2, eta=20, vtype=int),
        eliminate_duplicates=True,
    )
    result = minimize(problem, algorithm, ("n_gen", max(1, generations)), seed=seed, verbose=False)
    indices = [] if result.X is None else np.atleast_1d(result.X).astype(int).ravel().tolist()
    selected: list[dict[str, Any]] = []
    for index in indices:
        row = pool[min(max(index, 0), len(pool) - 1)]
        if row not in selected:
            selected.append(row)
    baseline = pool[0]
    if baseline not in selected:
        selected.insert(0, baseline)
    if len(selected) < size:
        selected_records = {row["record"] for row in selected}
        remaining = sorted(
            (row for row in pool if row["record"] not in selected_records),
            key=lambda row: tuple(row["objectives"]),
        )
        selected.extend(remaining[: size - len(selected)])
    return selected[:size]


def recommendation(population: list[dict[str, Any]], baseline: dict[str, Any], stage: str) -> dict[str, Any]:
    """Recommend only a non-dominated primary-objective candidate.

    The deterministic time-first tie break is applied only after Pareto
    filtering. It is not a weighted combination of the two objectives.
    """

    alternatives = [
        row
        for row in population
        if row["record"] != baseline["record"]
        and improved_over_baseline(row, baseline, stage)
    ]
    front = pareto_front([baseline, *alternatives], stage)
    alternatives = [row for row in front if row["record"] != baseline["record"]]
    if not alternatives:
        return baseline
    return min(
        alternatives,
        key=lambda row: (
            row["metrics"][f"{stage}_{PRIMARY_TIME_METRIC}"],
            -row["metrics"][f"{stage}_{PRIMARY_EFFICIENCY_METRIC}"],
            row["record"],
        ),
    )


def write_state(
    path: Path,
    population: list[dict[str, Any]],
    baseline: dict[str, Any],
    selected: dict[str, Any],
    pareto: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": 1,
        "protocol_id": PROTOCOL_ID,
        "protocol": PROTOCOL_METADATA,
        "objective_metrics": {
            "minimize": PRIMARY_TIME_METRIC,
            "maximize": PRIMARY_EFFICIENCY_METRIC,
        },
        "dataset": args.dataset,
        "stage": args.stage,
        "efficiency_kind": args.efficiency_kind,
        "baseline": baseline,
        "active_population": population,
        "pareto_front": pareto,
        "recommendation": selected,
    }
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            state["generation"] = int(previous.get("generation", 0)) + 1
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.population_size < 1 or args.generations < 1:
        raise SystemExit("population size and generations must be positive")
    records_root = args.records.resolve()
    rows = load_records(records_root, args.dataset, args.efficiency_kind)
    try:
        baseline = choose_baseline(rows, args.baseline)
    except EvolutionError as error:
        raise SystemExit(f"evolution unavailable: {error}") from error
    pool = candidate_pool(rows, baseline, args.stage)
    population = select_population(pool, args.population_size, args.generations, args.seed)
    selected = recommendation(population, baseline, args.stage)
    pareto = pareto_front(population, args.stage)
    write_state(args.state.resolve(), population, baseline, selected, pareto, args)

    result = {
        "recommended_candidate": selected["candidate"],
        "implementation_commit": selected["commit"],
        "record": selected["record"],
        "baseline_commit": baseline["commit"],
        "active_population": [row["candidate"] for row in population],
        "pareto_front": [row["candidate"] for row in pareto],
        "eligible_candidates": len(pool) - 1,
        "dataset": args.dataset,
        "stage": args.stage,
        "efficiency_kind": "particles",
        "objective_metrics": {
            "minimize": PRIMARY_TIME_METRIC,
            "maximize": PRIMARY_EFFICIENCY_METRIC,
        },
        "protocol_id": PROTOCOL_ID,
        "state": str(args.state.resolve()),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"recommended_candidate={result['recommended_candidate']}")
        print(f"implementation_commit={result['implementation_commit']}")
        print(f"active_population={','.join(result['active_population'])}")
        print(f"state={result['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
