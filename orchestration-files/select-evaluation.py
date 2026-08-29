#!/usr/bin/env python3
"""Select Genesis and four unique candidates using the two primary metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from objectives import (
    PRIMARY_EFFICIENCY_METRIC,
    PRIMARY_TIME_METRIC,
    SelectionError,
    choose_baseline,
    improved_over_baseline,
    is_active_row,
    load_records,
    pareto_front,
    time_first_key,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = PROJECT_ROOT / "records"
BASELINE = "Genesis"
TARGET_CANDIDATES = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--count", type=int, default=TARGET_CANDIDATES)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--names", action="store_true", help="print one selected candidate per line")
    return parser.parse_args()


def identity(row: dict[str, Any]) -> str:
    return row["commit"] or row["candidate"]


def deduplicate(rows: list[dict[str, Any]], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: item["record"], reverse=True):
        if row["candidate"] == baseline["candidate"] or identity(row) == identity(baseline):
            continue
        unique.setdefault(identity(row), row)
    return list(unique.values())


def rank_seeding_efficiency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (row for row in rows if is_active_row(row)),
        key=lambda row: (
            -row["metrics"][f"timed_{PRIMARY_EFFICIENCY_METRIC}"],
            *time_first_key(row),
        ),
    )


def rank_seeding_time(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((row for row in rows if is_active_row(row)), key=time_first_key)


def eligible_candidates(
    rows: list[dict[str, Any]], baseline: dict[str, Any]
) -> list[dict[str, Any]]:
    required = tuple(
        f"timed_{metric}" for metric in (PRIMARY_EFFICIENCY_METRIC, PRIMARY_TIME_METRIC)
    )
    return [
        row
        for row in deduplicate(rows, baseline)
        if all(key in row["metrics"] for key in required)
        and improved_over_baseline(row, baseline, "timed")
    ]


def choose(rows: list[dict[str, Any]], baseline_name: str, count: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("count must be positive")
    active_rows = [row for row in rows if is_active_row(row)]
    try:
        baseline = choose_baseline(active_rows, baseline_name)
    except SelectionError as error:
        raise ValueError(str(error)) from error
    candidates = eligible_candidates(active_rows, baseline)
    efficiency = rank_seeding_efficiency(candidates)
    seeding_time = rank_seeding_time(candidates)

    selected: list[dict[str, Any]] = [dict(baseline, selection_reason="baseline")]
    used = {identity(baseline)}

    def add_from(ranking: list[dict[str, Any]], reason: str, limit: int) -> None:
        added = 0
        for row in ranking:
            if identity(row) in used:
                continue
            selected.append(dict(row, selection_reason=reason))
            used.add(identity(row))
            added += 1
            if added == limit:
                return

    add_from(efficiency, "highest timed seeding particle efficiency", 2)
    add_from(seeding_time, "lowest timed seeding time per event", 2)

    if len(selected) < count + 1:
        for row in seeding_time:
            if identity(row) in used:
                continue
            selected.append(dict(row, selection_reason="next lowest timed seeding time per event"))
            used.add(identity(row))
            if len(selected) == count + 1:
                break

    if len(selected) != count + 1:
        raise ValueError(
            f"need {count} unique non-Genesis candidates plus {baseline_name}; "
            f"found {len(selected) - 1}"
        )
    return selected


def main() -> int:
    args = parse_args()
    rows = load_records(args.records.resolve(), "development")
    try:
        baseline = choose_baseline(rows, args.baseline)
        selected = choose(rows, args.baseline, args.count)
    except (SelectionError, ValueError) as error:
        raise SystemExit(f"evaluation selection failed: {error}") from error

    if args.names:
        for row in selected:
            print(row["candidate"])
        return 0

    result = {
        "baseline": args.baseline,
        "count": len(selected),
        "pareto_front": [
            row["candidate"]
            for row in pareto_front([baseline, *eligible_candidates(rows, baseline)])
        ],
        "candidates": [
            {
                "candidate": row["candidate"],
                "record": row["record"],
                "implementation_commit": row["commit"],
                "source_protocol_id": row.get("source_protocol_id", row.get("protocol_id")),
                "selection_reason": row["selection_reason"],
                "timed_seeding_particle_efficiency": row["metrics"].get("timed_seeding_particle_efficiency"),
                "timed_seeding_time_per_event_ms": row["metrics"].get("timed_seeding_time_per_event_ms"),
                "proposal": row.get("proposal"),
                "candidate_identity": row.get("candidate_identity"),
            }
            for row in selected
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else "\n".join(
        row["candidate"] for row in selected
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
