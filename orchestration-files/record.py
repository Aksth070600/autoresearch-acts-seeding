#!/usr/bin/env python3
"""Print the latest candidate result for an experiment agent."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECORDS_ROOT = PROJECT_ROOT / "records"
CATEGORIES = ("Development", "Evaluation", "Failed", "Errors")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate")
    parser.add_argument("--evaluation", action="store_true")
    parser.add_argument("--tail-lines", type=int, default=80)
    return parser.parse_args()


def validate_candidate(candidate: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", candidate):
        raise SystemExit("candidate name may contain only letters, numbers, '.', '_' and '-'")


def candidate_directories(candidate: str, evaluation: bool) -> list[Path]:
    preferred = ("Evaluation", "Errors") if evaluation else ("Development", "Failed")
    fallback = tuple(category for category in CATEGORIES if category not in preferred)
    for category in preferred + fallback:
        category_root = RECORDS_ROOT / category
        if not category_root.is_dir():
            continue
        canonical = category_root / candidate
        if (canonical / "summary.json").is_file():
            return [canonical]
        directories = [
            path for path in category_root.glob(f"*-{candidate}") if (path / "summary.json").is_file()
        ]
        if directories:
            return sorted(directories, key=lambda path: path.name, reverse=True)
    return []


def print_failure_logs(directory: Path, tail_lines: int) -> None:
    logs = sorted((directory / "logs").glob("*.log"))
    if not logs:
        return
    print("failure_logs:")
    for path in logs:
        print(f"--- {path.relative_to(PROJECT_ROOT)} ---")
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-tail_lines:]:
            print(line)


def main() -> int:
    args = parse_args()
    validate_candidate(args.candidate)
    if args.tail_lines < 1:
        raise SystemExit("--tail-lines must be positive")
    directories = candidate_directories(args.candidate, args.evaluation)
    if not directories:
        raise SystemExit(f"no result found for candidate: {args.candidate}")
    directory = directories[0]
    summary_path = directory / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    print(f"record_directory={directory.relative_to(PROJECT_ROOT)}")
    print("summary:")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary.get("status") != "passed" or summary.get("category") in {"Failed", "Errors"}:
        print_failure_logs(directory, args.tail_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
