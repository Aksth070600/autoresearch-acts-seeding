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

TIME_METRICS = ("total_time_per_event_ms", "seeding_time_per_event_ms")
ALGORITHMS = ("seeding", "ckf", "ambiguity")


class EvolutionError(RuntimeError):
    """Raised when the historical candidate pool cannot be evaluated."""


class HistoricalCandidateProblem(ElementwiseProblem):
    """Discrete NSGA-II problem whose decision variable indexes known records."""

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        super().__init__(
            n_var=1,
            n_obj=5,
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
    parser.add_argument("--baseline", default="baseline")
    parser.add_argument("--stage", choices=("clean", "timed"), default="timed")
    parser.add_argument("--efficiency-kind", choices=("particles", "tracks"), default="particles")
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


def flatten_summary(
    summary: dict[str, Any],
    path: Path,
    records_root: Path,
    efficiency_kind: str,
) -> dict[str, Any] | None:
    if summary.get("status") != "passed":
        return None
    metrics: dict[str, float] = {}
    for stage in summary.get("stages", []):
        if not isinstance(stage, dict):
            continue
        prefix = stage_prefix(stage)
        run_metrics = stage.get("run_metrics")
        if prefix is None or not isinstance(run_metrics, dict):
            continue
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
            value = values.get(f"efficiency_{efficiency_kind}")
            if finite(value):
                metrics[f"{prefix}_{algorithm}_efficiency"] = float(value)

    if not metrics:
        return None
    return {
        "candidate": str(summary.get("candidate_name", path.parent.name)),
        "category": str(summary.get("category", path.parent.parent.name)),
        "commit": str(summary.get("implementation_commit", "")),
        "record": path.relative_to(records_root).as_posix(),
        "metrics": metrics,
    }


def load_records(records_root: Path, dataset: str, efficiency_kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(records_root.glob("**/summary.json")):
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        category = str(summary.get("category", path.parent.parent.name)).lower()
        if dataset != "all" and category != dataset:
            continue
        row = flatten_summary(summary, path, records_root, efficiency_kind)
        if row is not None:
            rows.append(row)
    return rows


def choose_baseline(rows: list[dict[str, Any]], candidate_name: str) -> dict[str, Any]:
    matches = [row for row in rows if row["candidate"] == candidate_name]
    if not matches:
        raise EvolutionError(f"baseline candidate not found: {candidate_name}")
    development = [row for row in matches if row["category"].lower() == "development"]
    return (development or matches)[0]


def required_metrics(stage: str) -> tuple[str, ...]:
    return tuple(f"{stage}_{name}" for name in TIME_METRICS) + tuple(
        f"{stage}_{algorithm}_efficiency" for algorithm in ALGORITHMS
    )


def improved_over_baseline(row: dict[str, Any], baseline: dict[str, Any], stage: str) -> bool:
    metrics = row["metrics"]
    base = baseline["metrics"]
    if any(name not in metrics or name not in base for name in required_metrics(stage)):
        return False
    lower_time_gain = any(
        metrics[f"{stage}_{name}"] < base[f"{stage}_{name}"]
        for name in TIME_METRICS
    )
    higher_efficiency_gain = any(
        metrics[f"{stage}_{algorithm}_efficiency"] > base[f"{stage}_{algorithm}_efficiency"]
        for algorithm in ALGORITHMS
    )
    return lower_time_gain or higher_efficiency_gain


def objective_vector(row: dict[str, Any], stage: str) -> list[float]:
    metrics = row["metrics"]
    return [
        metrics[f"{stage}_total_time_per_event_ms"],
        metrics[f"{stage}_seeding_time_per_event_ms"],
        -metrics[f"{stage}_seeding_efficiency"],
        -metrics[f"{stage}_ckf_efficiency"],
        -metrics[f"{stage}_ambiguity_efficiency"],
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
    alternatives = [row for row in population if row["record"] != baseline["record"]]
    if not alternatives:
        return baseline
    base = baseline["metrics"]
    def score(row: dict[str, Any]) -> float:
        metrics = row["metrics"]
        score_value = 0.0
        for name in TIME_METRICS:
            denominator = max(abs(base[f"{stage}_{name}"]), 1e-12)
            score_value += (base[f"{stage}_{name}"] - metrics[f"{stage}_{name}"]) / denominator
        for algorithm in ALGORITHMS:
            denominator = max(abs(base[f"{stage}_{algorithm}_efficiency"]), 1e-12)
            score_value += (metrics[f"{stage}_{algorithm}_efficiency"] - base[f"{stage}_{algorithm}_efficiency"]) / denominator
        return score_value
    return max(alternatives, key=score)


def write_state(path: Path, population: list[dict[str, Any]], baseline: dict[str, Any], selected: dict[str, Any], args: argparse.Namespace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": 1,
        "dataset": args.dataset,
        "stage": args.stage,
        "efficiency_kind": args.efficiency_kind,
        "baseline": baseline,
        "active_population": population,
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
    baseline = choose_baseline(rows, args.baseline)
    pool = candidate_pool(rows, baseline, args.stage)
    population = select_population(pool, args.population_size, args.generations, args.seed)
    selected = recommendation(population, baseline, args.stage)
    write_state(args.state.resolve(), population, baseline, selected, args)

    result = {
        "recommended_candidate": selected["candidate"],
        "implementation_commit": selected["commit"],
        "record": selected["record"],
        "baseline_commit": baseline["commit"],
        "active_population": [row["candidate"] for row in population],
        "eligible_candidates": len(pool) - 1,
        "dataset": args.dataset,
        "stage": args.stage,
        "efficiency_kind": args.efficiency_kind,
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
