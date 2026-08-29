#!/usr/bin/env python3
"""Build exact owned-static v4 Development pilot views without reading v2/v3."""

from __future__ import annotations

import argparse
import html
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_ID = "acts-seeding-v4-owned-static"
PROTOCOL_REVISION = 2
RECORD_SCHEMA = "acts-v4-owned-static-development-record-v2"


def _load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or value.get("schema") != RECORD_SCHEMA
        or value.get("protocol_id") != PROTOCOL_ID
        or value.get("protocol_revision") != PROTOCOL_REVISION
        or value.get("category") != "Development"
    ):
        return None
    return value


def load_records(records: Path, dataset_id: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(records.glob("**/summary.json")):
        value = _load(path)
        if value is not None and value.get("dataset_id") == dataset_id:
            value["record_path"] = path.relative_to(records).as_posix()
            rows.append(value)
    return rows


def _rate(record: dict[str, Any]) -> Fraction:
    rate = record["result"]["rates"]["particle_efficiency"]
    return Fraction(rate["numerator"], rate["denominator"])


def _time(record: dict[str, Any]) -> int:
    return record["result"]["timing"]["per_event_nanoseconds"]


def pareto(records: list[dict[str, Any]]) -> list[str]:
    passed = [record for record in records if record.get("status") == "passed"]
    front = []
    for candidate in passed:
        dominated = any(
            other is not candidate
            and _time(other) <= _time(candidate)
            and _rate(other) >= _rate(candidate)
            and (_time(other) < _time(candidate) or _rate(other) > _rate(candidate))
            for other in passed
        )
        if not dominated:
            front.append(candidate)
    return [
        record["candidate_name"]
        for record in sorted(
            front, key=lambda row: (_time(row), -_rate(row), row["candidate_name"])
        )
    ]


def build_summary(
    records: list[dict[str, Any]], calibration: dict[str, Any], campaign: dict[str, Any]
) -> dict[str, Any]:
    genesis = [record for record in records if record["candidate_name"] == "Genesis"]
    candidates = sorted(
        (record for record in records if record["candidate_name"] != "Genesis"),
        key=lambda record: record["slot"],
    )
    if len(genesis) != 5 or [record["slot"] for record in candidates] != [1, 2, 3, 4]:
        raise SystemExit(
            "static-v4 report requires five Genesis and exact slots 1 through 4"
        )
    return {
        "schema": "acts-v4-owned-static-pilot-summary-v2",
        "protocol_id": PROTOCOL_ID,
        "protocol_revision": PROTOCOL_REVISION,
        "dataset_id": campaign["dataset"]["dataset_id"],
        "campaign": campaign,
        "genesis_calibration": calibration,
        "genesis_records": genesis,
        "candidates": candidates,
        "pareto_ranking": pareto(candidates),
        "scope": "Development on one fixed canonical 50-event dataset",
        "generalization": "No claim that this fixed dataset generalizes to other event populations.",
    }


def _fraction_text(value: dict[str, int]) -> str:
    return f"{value['numerator']}/{value['denominator']}"


def render(summary: dict[str, Any]) -> str:
    calibration = summary["genesis_calibration"]
    rows = []
    for record in summary["candidates"]:
        result = record["result"]
        classification = record["scientific_classification"]
        latency = record["latency"]
        rows.append(
            "<tr>"
            f"<td>{record['slot']}</td><td>{html.escape(record['candidate_name'])}</td>"
            f"<td>{html.escape(record['classification'])}</td>"
            f"<td><code>{html.escape(record['mechanism_key'])}</code></td>"
            f"<td>{result['timing']['per_event_nanoseconds'] / 1_000_000:.6f}</td>"
            f"<td>{html.escape(classification['timing']['label'])}</td>"
            f"<td>{result['stats']['nTotalMatchedParticles']}/{result['stats']['nTotalParticles']}</td>"
            f"<td>{result['stats']['nTotalFakeTracks']}/{result['stats']['nTotalTracks']}</td>"
            f"<td>{result['stats']['nTotalDuplicateTracks']}/{result['stats']['nTotalTracks']}</td>"
            f"<td>{latency['build_seconds']}</td>"
            f"<td>{latency['queue_to_immutable_record_seconds']}</td>"
            f"<td>{result['resources']['wall_seconds']}</td>"
            f"<td>{result['resources']['peak_rss_kb']}</td>"
            f"<td>{html.escape(classification['overall'])}</td>"
            "</tr>"
        )
    timings = ", ".join(
        f"{value / 1_000_000:.6f}"
        for value in calibration["genesis_per_event_nanoseconds"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Owned-static v4 pilot</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:1500px}}table{{border-collapse:collapse}}th,td{{border:1px solid #bbb;padding:.35rem;text-align:right}}th:nth-child(2),td:nth-child(2),th:nth-child(4),td:nth-child(4){{text-align:left}}code{{font-size:.85em}}</style></head>
<body><h1>ACTS Seeding owned-static v4 Development pilot</h1>
<p><b>Protocol:</b> <code>{html.escape(summary["protocol_id"])}</code><br>
<b>Protocol revision:</b> {summary["protocol_revision"]}<br>
<b>Dataset:</b> <code>{html.escape(summary["dataset_id"])}</code></p>
<p>Revision 1 evidence is preserved as invalid diagnostics and is excluded from every calibration, classification, ranking, and conclusion below.</p>
<h2>Genesis calibration</h2>
<p>Five timings (ms/event): {timings}<br>
Median G: {calibration["median_per_event_nanoseconds"] / 1_000_000:.6f} ms/event<br>
Empirical noise envelope u: {_fraction_text(calibration["relative_empirical_noise_envelope"])}. This is not a confidence level.</p>
<h2>Four deterministic candidates</h2>
<table><thead><tr><th>Slot</th><th>Candidate</th><th>Tier</th><th>Mechanism</th><th>ms/event</th><th>Timing class</th><th>Matched/selected</th><th>Fake/track</th><th>Duplicate/track</th><th>Build s</th><th>Total s</th><th>Wall s</th><th>Peak RSS KiB</th><th>Outcome</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
<p><b>Pareto time-first order:</b> {", ".join(map(html.escape, summary["pareto_ranking"])) or "none"}</p>
<p><b>Scope:</b> {html.escape(summary["generalization"])}</p>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=PROJECT_ROOT / "records")
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "build/site/static-v4/index.html"
    )
    args = parser.parse_args()
    campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    dataset_id = campaign["dataset"]["dataset_id"]
    records = load_records(args.records, dataset_id)
    summary = build_summary(records, calibration, campaign)
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(summary), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"included {len(records)} exact {PROTOCOL_ID} records for {dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
