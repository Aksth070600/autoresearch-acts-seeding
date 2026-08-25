#!/usr/bin/env python3
"""Select the Genesis baseline and four unique development candidates for evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evolution import load_records

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


def rank_ambiguity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (-row["metrics"]["timed_ambiguity_efficiency"], row["candidate"]),
    )


def rank_total_time(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (row["metrics"]["timed_total_time_per_event_ms"], row["candidate"]),
    )


def choose(rows: list[dict[str, Any]], baseline_name: str, count: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("count must be positive")
    baseline_matches = [row for row in rows if row["candidate"] == baseline_name]
    if not baseline_matches:
        raise ValueError(f"baseline candidate not found: {baseline_name}")
    baseline = baseline_matches[0]
    candidates = deduplicate(rows, baseline)
    required = ("timed_ambiguity_efficiency", "timed_total_time_per_event_ms")
    candidates = [row for row in candidates if all(key in row["metrics"] for key in required)]
    ambiguity = rank_ambiguity(candidates)
    total_time = rank_total_time(candidates)

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

    add_from(ambiguity, "highest timed ambiguity efficiency", 2)
    add_from(total_time, "lowest timed total time per event", 2)

    if len(selected) < count + 1:
        for row in total_time:
            if identity(row) in used:
                continue
            selected.append(dict(row, selection_reason="next lowest timed total time per event"))
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
    rows = load_records(args.records.resolve(), "development", "particles")
    try:
        selected = choose(rows, args.baseline, args.count)
    except ValueError as error:
        raise SystemExit(f"evaluation selection failed: {error}") from error

    if args.names:
        for row in selected:
            print(row["candidate"])
        return 0

    result = {
        "baseline": args.baseline,
        "count": len(selected),
        "candidates": [
            {
                "candidate": row["candidate"],
                "record": row["record"],
                "implementation_commit": row["commit"],
                "selection_reason": row["selection_reason"],
                "timed_ambiguity_efficiency": row["metrics"].get("timed_ambiguity_efficiency"),
                "timed_total_time_per_event_ms": row["metrics"].get("timed_total_time_per_event_ms"),
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
