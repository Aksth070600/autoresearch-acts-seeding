#!/usr/bin/env python3
"""Evaluate the selected historical implementations, including Genesis."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SELECTOR = PROJECT_ROOT / "orchestration-files" / "select-evaluation.py"
EVALUATOR = PROJECT_ROOT / "orchestration-files" / "evaluate.py"


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=PROJECT_ROOT, text=True, check=check)


def output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=PROJECT_ROOT, text=True).strip()


def ensure_clean() -> None:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            ".",
            ":(exclude)records",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    if result.stdout.strip():
        raise SystemExit("repository must be clean outside records before selected evaluation")


def select_candidates() -> list[dict[str, Any]]:
    result = subprocess.run(
        [sys.executable, str(SELECTOR), "--json"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)["candidates"]


def main() -> int:
    ensure_clean()
    original_branch = output(["git", "symbolic-ref", "--quiet", "--short", "HEAD"]) if subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0 else None
    original_commit = output(["git", "rev-parse", "HEAD"])
    candidates = select_candidates()
    restored = False

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        command = ["git", "checkout"] + (original_branch.split() if original_branch else ["--detach", original_commit])
        run(command)
        restored = True

    try:
        for candidate in candidates:
            name = candidate["candidate"]
            commit = candidate["implementation_commit"]
            print(f"selected_candidate={name} commit={commit}", flush=True)
            run(["git", "checkout", "--detach", commit])
            result = run([sys.executable, str(EVALUATOR), name, "--evaluation"], check=False)
            if result.returncode != 0:
                raise SystemExit(f"evaluation failed for {name}")
    finally:
        restore()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
