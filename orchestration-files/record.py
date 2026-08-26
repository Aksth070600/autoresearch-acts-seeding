#!/usr/bin/env python3
"""Print the latest candidate result for an experiment agent."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from protocol import is_compatible_summary

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


def compatible_summary(path: Path) -> bool:
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return is_compatible_summary(summary)


def record_recency(path: Path) -> tuple[datetime, str]:
    """Return a stable newest-first key for canonical and timestamped records."""

    try:
        summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary = {}
    for field in ("started_at", "finished_at"):
        value = summary.get(field)
        if isinstance(value, str):
            try:
                timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                else:
                    timestamp = timestamp.astimezone(timezone.utc)
                return (timestamp, path.name)
            except ValueError:
                pass

    match = re.match(r"(\d{8}T\d{6}(?:\d{6})?Z)(?:-\d+)?-", path.name)
    if match:
        timestamp = match.group(1)
        formats = ("%Y%m%dT%H%M%S%fZ", "%Y%m%dT%H%M%SZ")
        for date_format in formats:
            try:
                return (
                    datetime.strptime(timestamp, date_format).replace(tzinfo=timezone.utc),
                    path.name,
                )
            except ValueError:
                pass
    return (datetime.min.replace(tzinfo=timezone.utc), path.name)


def candidate_directories(
    candidate: str,
    evaluation: bool,
    records_root: Path | None = None,
) -> list[Path]:
    preferred = ("Evaluation", "Errors") if evaluation else ("Development", "Failed")
    fallback = tuple(category for category in CATEGORIES if category not in preferred)
    root = RECORDS_ROOT if records_root is None else records_root
    for category in preferred + fallback:
        category_root = root / category
        if not category_root.is_dir():
            continue
        directories = []
        canonical = category_root / candidate
        if (canonical / "summary.json").is_file() and compatible_summary(canonical / "summary.json"):
            directories.append(canonical)
        directories.extend(
            path
            for path in category_root.glob(f"*-{candidate}")
            if path != canonical
            and (path / "summary.json").is_file()
            and compatible_summary(path / "summary.json")
        )
        if directories:
            return sorted(directories, key=record_recency, reverse=True)
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
        raise SystemExit(
            f"no protocol-compatible result found for candidate: {args.candidate}"
        )
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
