#!/usr/bin/env python3
"""Render trusted public HTML from an exact active owned-static v4 status file."""

from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import subprocess
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

from visualizations.campaign import PLOTLY_SCRIPT_URL, visual_styles

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATUS_SCHEMA = "acts-v4-owned-static-continuous-status-v1"
PROTOCOL_ID = "acts-seeding-v4-owned-static"
PROTOCOL_REVISION = 2
DATASET_ID = (
    "acts-seeding-v4-owned-static-"
    "a05ae8663452d52dc2b90e2fa5372091a2cb04feb8cce86646da9f6ccbc2f3fb"
)
REPOSITORY_URL = "https://github.com/Aksth070600/autoresearch-acts-seeding"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CATEGORY_LABELS = {
    "major": "Major",
    "minor": "Minor",
    "combination": "Combination",
}


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _fraction(value: Any) -> Fraction | None:
    if not isinstance(value, dict):
        return None
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if (
        not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or not denominator
    ):
        return None
    return Fraction(numerator, denominator)


def _fraction_text(value: Any) -> str:
    fraction = _fraction(value)
    return (
        f"{fraction.numerator}/{fraction.denominator}"
        if fraction is not None
        else "unavailable"
    )


def _milliseconds(value: Any) -> float | None:
    return value / 1_000_000 if isinstance(value, int) else None


def _decimal(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _rate(stats: dict[str, Any], numerator: str, denominator: str) -> float | None:
    top = stats.get(numerator)
    bottom = stats.get(denominator)
    if not isinstance(top, int) or not isinstance(bottom, int) or bottom <= 0:
        return None
    return top / bottom


def _interval(value: Any) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    lower = _fraction(value.get("lower"))
    upper = _fraction(value.get("upper"))
    if lower is None or upper is None:
        return None
    return [float(lower / 1_000_000), float(upper / 1_000_000)]


def _validate(status: Any, deployed_commit: str) -> dict[str, Any]:
    if not isinstance(status, dict) or status.get("schema") != STATUS_SCHEMA:
        raise ValueError(
            "public dashboard accepts exact revision-2 static-v4 status only"
        )
    campaign = status.get("campaign")
    if (
        not isinstance(campaign, dict)
        or campaign.get("protocol_id") != PROTOCOL_ID
        or campaign.get("protocol_revision") != PROTOCOL_REVISION
        or campaign.get("dataset_id") != DATASET_ID
    ):
        raise ValueError(
            "public dashboard accepts exact revision-2 static-v4 status only"
        )
    if FULL_SHA.fullmatch(deployed_commit) is None:
        raise ValueError("deployed campaign commit must be a full Git SHA")
    if not isinstance(status.get("attempts"), list):
        raise ValueError("public static-v4 status attempts must be an array")
    return status


def _lineage(proposal: Any) -> list[dict[str, str]]:
    if not isinstance(proposal, dict):
        return []
    sources: list[dict[str, str]] = []
    derives_from = proposal.get("derives_from")
    if isinstance(derives_from, dict):
        sources.append(
            {
                "relation": "derives from",
                "candidate": str(derives_from.get("candidate", "unknown")),
                "mechanism_key": str(derives_from.get("mechanism_key", "unknown")),
                "implementation_commit": str(
                    derives_from.get("implementation_commit", "")
                ),
            }
        )
    combination = proposal.get("combination_provenance")
    if isinstance(combination, dict):
        for source in combination.get("sources", []):
            if isinstance(source, dict):
                sources.append(
                    {
                        "relation": "combines",
                        "candidate": str(source.get("candidate", "unknown")),
                        "mechanism_key": str(source.get("mechanism_key", "unknown")),
                        "implementation_commit": str(
                            source.get("implementation_commit", "")
                        ),
                    }
                )
    return sources


def _attempt_model(attempt: dict[str, Any]) -> dict[str, Any]:
    stats = attempt.get("stats") if isinstance(attempt.get("stats"), dict) else {}
    timing = attempt.get("timing") if isinstance(attempt.get("timing"), dict) else {}
    scientific = (
        attempt.get("scientific_classification")
        if isinstance(attempt.get("scientific_classification"), dict)
        else {}
    )
    timing_class = scientific.get("timing")
    if not isinstance(timing_class, dict):
        timing_class = {}
    efficiency_class = scientific.get("efficiency")
    if not isinstance(efficiency_class, dict):
        efficiency_class = {}
    genesis_efficiency = _fraction(efficiency_class.get("genesis"))
    latency = attempt.get("latency") if isinstance(attempt.get("latency"), dict) else {}
    resources = (
        attempt.get("resources") if isinstance(attempt.get("resources"), dict) else {}
    )
    proposal = (
        attempt.get("proposal") if isinstance(attempt.get("proposal"), dict) else {}
    )
    commit = str(attempt.get("implementation_commit", ""))
    return {
        "slot": attempt.get("slot"),
        "record_path": attempt.get("record_path"),
        "candidate": str(attempt.get("candidate", "unknown")),
        "classification": str(attempt.get("classification", "unknown")),
        "mechanism_key": str(attempt.get("mechanism_key", "unknown")),
        "status": str(attempt.get("status", "invalid")),
        "implementation_commit": commit,
        "commit_url": f"{REPOSITORY_URL}/commit/{commit}"
        if FULL_SHA.fullmatch(commit)
        else None,
        "timing_ms": _milliseconds(timing.get("per_event_nanoseconds")),
        "candidate_interval_ms": _interval(
            timing_class.get("candidate_interval_nanoseconds")
        ),
        "genesis_interval_ms": _interval(
            timing_class.get("genesis_interval_nanoseconds")
        ),
        "timing_classification": str(timing_class.get("label", "invalid")),
        "overall": str(scientific.get("overall", "invalid")),
        "efficiency": _rate(stats, "nTotalMatchedParticles", "nTotalParticles"),
        "genesis_efficiency": (
            float(genesis_efficiency) if genesis_efficiency is not None else None
        ),
        "fake_rate": _rate(stats, "nTotalFakeTracks", "nTotalTracks"),
        "duplicate_rate": _rate(stats, "nTotalDuplicateTracks", "nTotalTracks"),
        "counts": {
            "matched": stats.get("nTotalMatchedParticles"),
            "selected": stats.get("nTotalParticles"),
            "fake": stats.get("nTotalFakeTracks"),
            "duplicate": stats.get("nTotalDuplicateTracks"),
            "tracks": stats.get("nTotalTracks"),
        },
        "latency": {
            "preparation_seconds": _decimal(latency.get("preparation_seconds")),
            "build_seconds": _decimal(latency.get("build_seconds")),
            "process_seconds": _decimal(resources.get("wall_seconds")),
            "queue_to_record_seconds": _decimal(
                latency.get("queue_to_immutable_record_seconds")
            ),
        },
        "peak_rss_kb": resources.get("peak_rss_kb"),
        "lineage": _lineage(proposal),
        "changed_symbols": proposal.get("changed_symbols", []),
    }


def _format_rate(value: float | None) -> str:
    return f"{value * 100:.3f}%" if value is not None else "Unavailable"


def _instant(value: Any) -> datetime | None:
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None else None


def _format_instant(value: datetime | None) -> str:
    if value is None:
        return "Unavailable"
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return f"{months[value.month - 1]} {value.day}, {value.year}, {value:%H:%M} UTC"


def _format_duration(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    seconds = max(0, round(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _humanize_candidate(value: str) -> str:
    value = re.sub(r"V4C$", "", value)
    words = re.sub(r"[_-]+", " ", value)
    words = re.sub(r"([a-z0-9])([A-Z][a-z])", r"\1 \2", words)
    return re.sub(r"\s+", " ", words).strip()


def _campaign_label(campaign: dict[str, Any], control: dict[str, Any]) -> str:
    lifecycle = "Running" if control.get("state") == "open" else "Completed"
    started = str(campaign.get("started_at", ""))
    try:
        year, month, day = (int(part) for part in started[:10].split("-"))
        month_name = (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        )[month - 1]
        date = f" · {month_name} {day}, {year}"
    except (ValueError, IndexError):
        date = ""
    return f"{lifecycle} · ACTS Seeding Campaign{date}"


def _progress_card(label: str, value: str, percentage: float, note: str = "") -> str:
    safe_percentage = max(0.0, min(percentage, 100.0))
    note_html = f'<span class="card-note">{_escape(note)}</span>' if note else ""
    return (
        '<div class="card">'
        f'<span class="card-label">{_escape(label)}</span>'
        f'<strong class="card-value">{_escape(value)}</strong>{note_html}'
        '<div class="progress-track">'
        f'<span class="progress-fill" style="width:{safe_percentage:.2f}%"></span>'
        "</div></div>"
    )


def _result_card(attempt: dict[str, Any], genesis_ms: float | None) -> str:
    delta = (
        attempt["timing_ms"] - genesis_ms
        if attempt["timing_ms"] is not None and genesis_ms is not None
        else None
    )
    delta_text = (
        f"{delta:+.3f} ms ({delta / genesis_ms * 100:+.3f}%)"
        if delta is not None and genesis_ms
        else "Genesis comparison unavailable"
    )
    timing_text = (
        f"{attempt['timing_ms']:.3f} ms"
        if attempt["timing_ms"] is not None
        else "Unavailable"
    )
    body = (
        f'<span class="card-name">{_escape(_humanize_candidate(attempt["candidate"]))}</span>'
        f'<strong class="card-value">{_escape(timing_text)}</strong>'
        f'<span class="card-note">{_escape(delta_text)}</span>'
    )
    if attempt["commit_url"]:
        return (
            f'<a class="card result-card" href="{_escape(attempt["commit_url"])}" '
            f'target="_blank" rel="noopener noreferrer">{body}</a>'
        )
    return f'<div class="card result-card">{body}</div>'


def _completion_times(
    status: dict[str, Any], deployed_commit: str, repository_root: Path
) -> dict[int, datetime]:
    completed: dict[int, datetime] = {}
    for attempt in status.get("attempts", []):
        slot = attempt.get("slot") if isinstance(attempt, dict) else None
        record_path = attempt.get("record_path") if isinstance(attempt, dict) else None
        if not isinstance(slot, int) or not isinstance(record_path, str):
            continue
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "log",
                "-1",
                "--diff-filter=A",
                "--format=%cI",
                deployed_commit,
                "--",
                record_path,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        instant = _instant(result.stdout.strip()) if result.returncode == 0 else None
        if instant is not None:
            completed[slot] = instant
    return completed


def _review_panel() -> str:
    return """
<section class="lavish-review" data-container="Captain visual decision">
  <form data-lavish-question="visual-acceptance" onsubmit="event.preventDefault(); const data = new FormData(event.currentTarget); const decision = data.get('decision'); const note = data.get('note'); if (decision) window.lavish.queuePrompt(`Visual review: ${decision}.${note ? ` ${note}` : ''}`, {tag:'visual-decision', text:`${decision}${note ? ` · ${note}` : ''}`, queueKey:'visual-acceptance', element:event.currentTarget, data:{decision,note}});">
    <strong>Captain visual review</strong>
    <span class="note">Choose a decision, add optional direction, queue it, then use Send or Send &amp; End.</span>
    <div class="review-options"><label><input type="radio" name="decision" value="Approve this campaign design"> Approve</label><label><input type="radio" name="decision" value="Revise this campaign design"> Revise</label></div>
    <textarea name="note" rows="2" placeholder="Optional visual direction"></textarea>
    <button type="submit">Queue visual decision</button>
  </form>
</section>"""


def public_campaign_model(status: dict[str, Any], deployed_commit: str) -> dict[str, Any]:
    """Build a display model without mixing static-v4 evidence into v3 rows."""

    status = _validate(status, deployed_commit)
    campaign = status["campaign"]
    attempts = [_attempt_model(attempt) for attempt in status["attempts"]]
    calibration = (
        status.get("calibration") if isinstance(status.get("calibration"), dict) else {}
    )
    genesis_ms = _milliseconds(calibration.get("median_per_event_nanoseconds"))
    genesis_timings = [
        value
        for value in (
            _milliseconds(item)
            for item in calibration.get("genesis_per_event_nanoseconds", [])
        )
        if value is not None
    ]
    genesis_interval = next(
        (
            attempt["genesis_interval_ms"]
            for attempt in attempts
            if attempt["genesis_interval_ms"]
        ),
        [min(genesis_timings), max(genesis_timings)] if genesis_timings else None,
    )
    genesis_efficiency = next(
        (
            attempt["genesis_efficiency"]
            for attempt in attempts
            if attempt["genesis_efficiency"] is not None
        ),
        None,
    )
    passed = [
        attempt
        for attempt in attempts
        if attempt["status"] == "passed" and attempt["timing_ms"] is not None
    ]
    control = status.get("control") if isinstance(status.get("control"), dict) else {}
    composition = (
        status.get("composition") if isinstance(status.get("composition"), dict) else {}
    )
    return {
        "campaign": {
            "campaign_id": campaign.get("campaign_id"),
            "branch": campaign.get("branch"),
            "control_id": campaign.get("control_id"),
            "protocol_id": campaign.get("protocol_id"),
            "protocol_revision": campaign.get("protocol_revision"),
            "dataset_id": campaign.get("dataset_id"),
            "platform_commit": campaign.get("platform_commit"),
            "scientific_genesis_commit": campaign.get("scientific_genesis_commit"),
            "acts_commit": campaign.get("acts_commit"),
            "deployed_commit": deployed_commit,
        },
        "genesis": {
            "median_ms": genesis_ms,
            "timings_ms": genesis_timings,
            "interval_ms": genesis_interval,
            "efficiency": genesis_efficiency,
            "empirical_envelope": _fraction_text(
                calibration.get("relative_empirical_noise_envelope")
            ),
            "peak_rss_kb": calibration.get("median_peak_rss_kb"),
        },
        "composition": composition,
        "terminal_status": control.get("state", "unknown"),
        "completed_at": control.get("completed_at"),
        "best_attempt": min(
            passed, key=lambda attempt: (attempt["timing_ms"], attempt["slot"])
        ) if passed else None,
        "terminal_attempt": attempts[-1] if attempts else None,
        "attempts": attempts,
    }


def archive_styles() -> str:
    return """
    .archive { margin-top: 28px; padding-top: 20px; border-top: 1px solid #334155; }
    .archive h2, .archive h3 { margin-bottom: 8px; }
    .archive-summary { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; margin: 14px 0; }
    .archive-card { display: grid; gap: 4px; padding: 12px; background: #111827; border: 1px solid #334155; border-radius: 10px; }
    .archive-label { color: #94a3b8; font-size: .75rem; font-weight: 700; text-transform: uppercase; }
    .archive-ledger { width: 100%; border-collapse: collapse; font-size: .78rem; }
    .archive-ledger th, .archive-ledger td { padding: 7px; border-bottom: 1px solid #334155; text-align: left; vertical-align: top; }
    .archive-ledger th { position: sticky; top: 0; background: #111827; color: #c4b5fd; }
    .archive-table-wrap { max-height: 720px; overflow: auto; border: 1px solid #334155; border-radius: 10px; }
    .archive code { overflow-wrap: anywhere; }
    .archive a { color: #a5b4fc; }
    @media (max-width: 800px) { .archive-summary { grid-template-columns: 1fr 1fr; } .archive-table-wrap { overflow-x: auto; } }
    """


def render_archive(model: dict[str, Any], *, heading_level: int = 2) -> str:
    """Render the immutable terminal campaign as a separate evidence section."""

    campaign = model["campaign"]
    attempts = model["attempts"]
    counts = model.get("composition", {}).get("counts", {})
    genesis = model["genesis"]
    best = model.get("best_attempt") or {}
    terminal = model.get("terminal_attempt") or {}
    commit_links = []
    for label, key in (
        ("Archive", "deployed_commit"),
        ("Platform", "platform_commit"),
        ("Scientific Genesis", "scientific_genesis_commit"),
        ("ACTS", "acts_commit"),
    ):
        commit = str(campaign.get(key, ""))
        if FULL_SHA.fullmatch(commit):
            commit_links.append(
                f'<a href="{REPOSITORY_URL}/commit/{commit}" target="_blank" '
                f'rel="noopener noreferrer">{_escape(label)} {_escape(commit[:7])}</a>'
            )
    rows = []
    for attempt in attempts:
        timing = attempt.get("timing_ms")
        counts_data = attempt.get("counts", {})
        latency = attempt.get("latency", {})
        commit = attempt.get("implementation_commit", "")
        mechanism = _escape(attempt.get("mechanism_key", "unknown"))
        if attempt.get("commit_url"):
            mechanism = (
                f'<a href="{_escape(attempt["commit_url"])}" target="_blank" '
                f'rel="noopener noreferrer">{mechanism}</a><br><code>{_escape(str(commit)[:12])}</code>'
            )
        physics = (
            f'E {_format_rate(attempt.get("efficiency"))}<br>'
            f'F {_format_rate(attempt.get("fake_rate"))}<br>'
            f'D {_format_rate(attempt.get("duplicate_rate"))}<br>'
            f'matched {counts_data.get("matched", "n/a")} / selected {counts_data.get("selected", "n/a")}'
        )
        latency_text = "<br>".join(
            f'{label} {value:.3f}s' if isinstance(value, (int, float)) else f'{label} n/a'
            for label, value in (
                ("prep", latency.get("preparation_seconds")),
                ("build", latency.get("build_seconds")),
                ("process", latency.get("process_seconds")),
                ("queue-record", latency.get("queue_to_record_seconds")),
            )
        )
        rss = attempt.get("peak_rss_kb")
        rss_text = f"{rss / 1024 / 1024:.2f} GiB" if isinstance(rss, (int, float)) else "n/a"
        rows.append(
            "<tr>"
            f'<td>{_escape(attempt.get("slot"))}</td>'
            f'<td>{_escape(attempt.get("classification"))}</td>'
            f'<td><strong>{_escape(attempt.get("status"))}</strong><br>{_escape(attempt.get("overall"))}</td>'
            f'<td>{_escape(attempt.get("candidate"))}</td><td>{mechanism}</td>'
            f'<td>{f"{timing:.3f} ms/event" if isinstance(timing, (int, float)) else "n/a"}<br>{_escape(attempt.get("timing_classification"))}</td>'
            f'<td>{physics}</td><td>{latency_text}<br>RSS {rss_text}</td>'
            f'<td><code>{_escape(attempt.get("record_path"))}</code></td></tr>'
        )
    heading = f"h{heading_level}"
    genesis_ms = genesis.get("median_ms")
    return f"""
<section class="archive" id="terminal-static-v4" data-attempt-count="{len(attempts)}" data-terminal-status="{_escape(model.get('terminal_status'))}">
  <{heading}>Terminal owned-static v4 campaign</{heading}>
  <p>Immutable protocol-isolated archive. It is displayed separately and is not imported into v3 ranking or conclusions.</p>
  <p><strong>Campaign ID:</strong> <code>{_escape(campaign.get('campaign_id'))}</code><br>{' · '.join(commit_links)}</p>
  <div class="archive-summary">
    <div class="archive-card"><span class="archive-label">Terminal status</span><strong>{_escape(model.get('terminal_status')).title()}</strong></div>
    <div class="archive-card"><span class="archive-label">Attempts</span><strong>{len(attempts)}</strong><span>{counts.get('major', 0)} major / {counts.get('minor', 0)} minor / {counts.get('combination', 0)} combination</span></div>
    <div class="archive-card"><span class="archive-label">Genesis</span><strong>{genesis_ms:.3f} ms/event</strong><span>Peak RSS {genesis.get('peak_rss_kb', 0) / 1024 / 1024:.2f} GiB</span></div>
    <div class="archive-card"><span class="archive-label">Best / terminal result</span><strong>{best.get('timing_ms'):.3f} / {terminal.get('timing_ms'):.3f} ms/event</strong><span>slots {best.get('slot')} / {terminal.get('slot')}</span></div>
  </div>
  <details open><summary><strong>All {len(attempts)} attempts, including invalid and crash evidence</strong></summary>
  <div class="archive-table-wrap"><table class="archive-ledger"><thead><tr><th>Slot</th><th>Class</th><th>Status</th><th>Candidate</th><th>Mechanism / commit</th><th>Timing</th><th>Physics</th><th>Latency / resource</th><th>Immutable record</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details>
</section>"""


def render(
    status: dict[str, Any],
    *,
    deployed_commit: str,
    plotly_src: str = PLOTLY_SCRIPT_URL,
    review_mode: bool = False,
    completion_times: dict[int, datetime] | None = None,
) -> str:
    status = _validate(status, deployed_commit)
    payload = public_campaign_model(status, deployed_commit)
    campaign = status["campaign"]
    attempts = payload["attempts"]
    calibration = (
        status.get("calibration") if isinstance(status.get("calibration"), dict) else {}
    )
    genesis_ms = payload["genesis"]["median_ms"]
    baseline = (
        calibration.get("baseline")
        if isinstance(calibration.get("baseline"), dict)
        else {}
    )
    baseline_stats = (
        baseline.get("stats") if isinstance(baseline.get("stats"), dict) else {}
    )
    genesis_efficiency_summary = _rate(
        baseline_stats, "nTotalMatchedParticles", "nTotalParticles"
    )
    composition = (
        status.get("composition") if isinstance(status.get("composition"), dict) else {}
    )
    counts = (
        composition.get("counts") if isinstance(composition.get("counts"), dict) else {}
    )
    completed = len(attempts)
    started_at = _instant(campaign.get("started_at"))
    generated_at = _instant(status.get("generated_at"))
    elapsed_seconds = (
        max((generated_at - started_at).total_seconds(), 0)
        if started_at is not None and generated_at is not None
        else None
    )
    ordered_completions = [
        completion_times[attempt["slot"]]
        for attempt in attempts
        if completion_times is not None and attempt["slot"] in completion_times
    ]
    finish_intervals = [
        max((current - previous).total_seconds(), 0)
        for previous, current in zip(ordered_completions, ordered_completions[1:])
    ]
    median_candidate_duration = (
        statistics.median(finish_intervals) if finish_intervals else None
    )
    denominator = max(completed, 1)
    progress_cards = []
    for category, target in (("major", 50), ("minor", 25), ("combination", 25)):
        count = (
            counts.get(category, 0) if isinstance(counts.get(category, 0), int) else 0
        )
        actual = count / denominator * 100
        progress_cards.append(
            _progress_card(
                f"{CATEGORY_LABELS[category]} candidates",
                str(count),
                actual / target * 100,
                f"{actual:.1f}% completed / {target}% target",
            )
        )

    passed = [
        attempt
        for attempt in attempts
        if attempt["status"] == "passed" and attempt["timing_ms"] is not None
    ]
    leaders = sorted(
        passed, key=lambda attempt: (attempt["timing_ms"], attempt["slot"])
    )[:3]
    result_cards = "".join(_result_card(attempt, genesis_ms) for attempt in leaders)
    if not result_cards:
        result_cards = '<div class="card"><strong class="card-value">Waiting for complete Development evidence.</strong></div>'
    genesis_peak_rss_kb = calibration.get("median_peak_rss_kb")
    genesis_peak_rss = (
        f"{genesis_peak_rss_kb / 1024 / 1024:.2f} GiB"
        if isinstance(genesis_peak_rss_kb, int)
        else "Unavailable"
    )

    script_data = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    control = status.get("control") if isinstance(status.get("control"), dict) else {}
    scheduler = (
        status.get("scheduler") if isinstance(status.get("scheduler"), dict) else {}
    )
    finish_url = (
        f"{REPOSITORY_URL}/actions/workflows/finish-campaign.yml?query=branch%3Amain"
    )
    extra_styles = """
    .progress-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .finish-heading-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
    .finish-guidance { color: #cbd5e1; font-size: .86rem; }
    .identity-boxes { display: grid; gap: 7px; margin-top: 10px !important; }
    .identity-row { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 7px; }
    .identity-label, .identity-value { min-width: 0; padding: 7px 10px; border: 1px solid #475569; border-radius: 8px; background: #1e293b; }
    .identity-label { color: #cbd5e1; font-size: .7rem; letter-spacing: .05em; text-transform: uppercase; }
    .identity-value { color: #f8fafc; overflow-wrap: anywhere; }
    .timing-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    #corner-overlays { position: absolute; inset: 28px 30px; z-index: 10; pointer-events: none; }
    .corner-stack { position: absolute; display: grid; gap: 5px; }
    .corner-stack.top-left { top: 18px; left: 49px; }
    .corner-stack.top-right { top: 18px; right: 2px; justify-items: end; }
    .corner-stack.bottom-left { bottom: 30px; left: 49px; justify-items: start; }
    .corner-stack.bottom-right { right: 2px; bottom: 30px; justify-items: end; }
    .corner-badge { width: max-content; padding: 4px 8px; border: 1px solid; border-radius: 999px; font-size: .72rem; font-weight: 750; letter-spacing: .03em; }
    .corner-badge.better { background: rgba(34,197,94,.85); border-color: #4ade80; color: #052e16; }
    .corner-badge.worse { background: rgba(239,68,68,.85); border-color: #f87171; color: #450a0a; }
    .lavish-review { max-width: 1920px; margin: 0 auto 28px; padding: 0 24px; }
    .lavish-review form { display: grid; gap: 10px; padding: 16px; border: 1px dashed #818cf8; border-radius: 10px; background: #111827; }
    .review-options { display: flex; flex-wrap: wrap; gap: 16px; }
    .review-options label { display: flex; grid-template-columns: auto 1fr; align-items: center; }
    .lavish-review textarea { width: 100%; resize: vertical; border: 1px solid #475569; border-radius: 6px; padding: 8px 10px; background: #1e293b; color: #e5e7eb; font: inherit; }
    .lavish-review button { width: max-content; padding: 8px 12px; border: 1px solid #818cf8; border-radius: 7px; background: #3730a3; color: #fff; font: inherit; font-weight: 700; }
    @media (max-width: 700px) { .identity-row { grid-template-columns: 1fr; gap: 3px; } #corner-overlays { inset: 16px; } .corner-badge { font-size: .64rem; } }
    """
    review_panel = _review_panel() if review_mode else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ACTS Seeding Campaign · Live Dashboard</title>
<script src="{_escape(plotly_src)}"></script>
<style>{visual_styles()}\n{extra_styles}\n{archive_styles()}</style></head>
<body><main><h1>ACTS Seeding Live Campaign</h1>
<section class="controls" aria-label="Campaign selection"><label>Campaign<select id="campaign-select" disabled><option>{_escape(_campaign_label(campaign, control))}</option></select></label>
<section id="finish-control" class="finish-control" aria-label="Continuous campaign finish control"><div><div class="finish-heading-line"><strong id="finish-heading">Finish campaign</strong><span id="finish-status" class="finish-guidance">(Open the authenticated GitHub workflow, choose main, enter the exact identity below, then confirm Run workflow.)</span></div><div id="finish-identity" class="control-identity identity-boxes"><span class="identity-row"><b class="identity-label">Branch</b><code class="identity-value">{_escape(campaign.get("branch"))}</code></span><span class="identity-row"><b class="identity-label">Campaign ID</b><code class="identity-value">{_escape(campaign.get("campaign_id"))}</code></span><span class="identity-row"><b class="identity-label">Control ID</b><code class="identity-value">{_escape(campaign.get("control_id"))}</code></span></div></div><a id="finish-button" class="finish-button" href="{finish_url}" target="_blank" rel="noopener noreferrer">Finish campaign</a></section></section>
<div id="dashboard" data-attempt-count="{completed}"><div class="campaign-heading"><h2>ACTS Seeding Campaign</h2><div class="chips"><span class="chip good">{_escape("Running" if control.get("state") == "open" else "Completed")}</span><span class="chip">Next · {_escape(scheduler.get("next_category", "none"))}</span></div></div>
<section class="grid progress-grid" aria-label="Campaign progress">{"".join(progress_cards)}</section>
<section class="grid timing-grid" aria-label="Campaign timing"><div class="card"><span class="card-label">Campaign start</span><strong class="card-value">{_escape(_format_instant(started_at))}</strong></div><div class="card"><span class="card-label">Time elapsed</span><strong class="card-value">{_escape(_format_duration(elapsed_seconds))}</strong></div><div class="card"><span class="card-label">Time per experiment</span><strong class="card-value">{_escape(_format_duration(median_candidate_duration))}</strong></div></section>
<section class="section" aria-labelledby="baseline-heading"><h2 id="baseline-heading">Baseline</h2><div class="grid timing-grid" aria-label="Campaign baseline metrics"><div class="card"><span class="card-label">Time per event</span><strong class="card-value">{f"{genesis_ms:.3f} ms" if genesis_ms is not None else "Unavailable"}</strong></div><div class="card"><span class="card-label">Seeding efficiency</span><strong class="card-value">{_escape(_format_rate(genesis_efficiency_summary))}</strong></div><div class="card"><span class="card-label">Peak RSS</span><strong class="card-value">{_escape(genesis_peak_rss)}</strong></div></div></section>
<section class="section" aria-labelledby="results-heading"><div class="section-heading"><h2 id="results-heading">Promising Early Results</h2></div><div class="grid results-grid">{result_cards}</div></section>
<section class="section" aria-label="Campaign results comparison"><div id="chart-frame"><div id="plot-empty" hidden>Interactive chart library could not be loaded.</div><div id="chart" role="img" aria-label="Interactive owned-static v4 candidate comparison chart"></div><div id="corner-overlays" aria-hidden="true"><div class="corner-stack top-left"><span class="corner-badge better">Faster</span><span class="corner-badge better">Higher efficiency</span></div><div class="corner-stack top-right"><span class="corner-badge worse">Slower</span><span class="corner-badge better">Higher efficiency</span></div><div class="corner-stack bottom-left"><span class="corner-badge better">Faster</span><span class="corner-badge worse">Lower efficiency</span></div><div class="corner-stack bottom-right"><span class="corner-badge worse">Slower</span><span class="corner-badge worse">Lower efficiency</span></div></div></div></section>
{render_archive(payload, heading_level=2)}
</div></main>{review_panel}
<script>
const CAMPAIGN = {script_data};
const plotEmpty = document.getElementById('plot-empty');
const pointColors = {{good:'#22c55e', mixed:'#eab308', bad:'#ef4444', unavailable:'#94a3b8', baseline:'#fbbf24'}};
function validCommitUrl(value) {{ return typeof value === 'string' && /^https:\\/\\/github\\.com\\/Aksth070600\\/autoresearch-acts-seeding\\/commit\\/[0-9a-f]{{40}}$/.test(value); }}
function formatPercent(value) {{ return Number.isFinite(value) ? `${{(value*100).toFixed(3)}}%` : 'n/a'; }}
function formatRss(value) {{ return Number.isFinite(value) ? `${{(value/1024/1024).toFixed(2)}} GiB` : 'n/a'; }}
function escapeHtml(value) {{ return String(value).replace(/[&<>"']/g, character => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[character]); }}
function displayName(value) {{ return String(value).replace(/V4C$/,'').replace(/[_-]+/g,' ').replace(/([a-z0-9])([A-Z][a-z])/g,'$1 $2').replace(/\\s+/g,' ').trim(); }}
function tooltip(attempt) {{
  const interval=attempt.candidate_interval_ms ? `${{attempt.candidate_interval_ms[0].toFixed(3)}}–${{attempt.candidate_interval_ms[1].toFixed(3)}} ms` : 'n/a';
  const decision=attempt.overall==='valid improvement'?'Improvement':attempt.overall==='regression'?'Regression':attempt.candidate==='Genesis'?'Baseline':'Inconclusive';
  return `<b>${{escapeHtml(displayName(attempt.candidate))}}</b><br><span style="font-family:monospace">T&nbsp;&nbsp;${{attempt.timing_ms?.toFixed(3) ?? 'n/a'}} ms (${{interval}})<br>E&nbsp;&nbsp;${{formatPercent(attempt.efficiency)}}<br>F&nbsp;&nbsp;${{formatPercent(attempt.fake_rate)}}<br>D&nbsp;&nbsp;${{formatPercent(attempt.duplicate_rate)}}<br>RSS&nbsp;&nbsp;${{formatRss(attempt.peak_rss_kb)}}<br>Decision: ${{decision}}</span>`;
}}
function renderChart() {{
  const candidates=CAMPAIGN.attempts.filter(attempt=>Number.isFinite(attempt.timing_ms)&&Number.isFinite(attempt.efficiency));
  const genesis={{candidate:'Genesis',timing_ms:CAMPAIGN.genesis.median_ms,efficiency:CAMPAIGN.genesis.efficiency,candidate_interval_ms:CAMPAIGN.genesis.interval_ms,overall:'baseline',commit_url:''}};
  const points=Number.isFinite(genesis.timing_ms)&&Number.isFinite(genesis.efficiency)?[...candidates,genesis]:candidates;
  if (!points.length || typeof Plotly === 'undefined') {{ if(typeof Plotly!=='undefined') Plotly.purge('chart'); plotEmpty.hidden=false; return; }}
  plotEmpty.hidden=true;
  const xValues=points.map(point=>point.timing_ms); const yValues=points.map(point=>point.efficiency); const gx=CAMPAIGN.genesis.median_ms,gy=CAMPAIGN.genesis.efficiency;
  const xMin=Math.min(...xValues),xMax=Math.max(...xValues),xSpan=xMax-xMin||1; const yMin=Math.min(...yValues),yMax=Math.max(...yValues),ySpan=yMax-yMin||Math.max(Math.abs(yMax),1); const xRange=[xMin-xSpan*.2,xMax+xSpan*.2],yRange=[yMin-ySpan*.2,yMax+ySpan*.2];
  const widths=candidates.map(row=>row.candidate_interval_ms?row.candidate_interval_ms[1]-row.candidate_interval_ms[0]:0); const minWidth=Math.min(...widths),maxWidth=Math.max(...widths),widthSpan=maxWidth-minWidth||1; const pointSize=row=>row.candidate==='Genesis'?18:12+8*((row.candidate_interval_ms?row.candidate_interval_ms[1]-row.candidate_interval_ms[0]:minWidth)-minWidth)/widthSpan;
  const baselineColor=row=>{{if(row.candidate==='Genesis')return pointColors.baseline;const faster=row.timing_ms<=genesis.timing_ms,moreEfficient=row.efficiency>=genesis.efficiency;if(faster&&moreEfficient)return pointColors.good;if(!faster&&!moreEfficient)return pointColors.bad;return pointColors.mixed;}};
  const trace={{x:points.map(row=>row.timing_ms),y:points.map(row=>row.efficiency),text:points.map(tooltip),customdata:points.map(row=>row.commit_url||''),mode:'markers',type:'scatter',name:'Candidates',marker:{{size:points.map(pointSize),symbol:points.map(row=>row.candidate==='Genesis'?'star':'circle'),color:points.map(baselineColor),line:{{width:1,color:'#e2e8f0'}}}},hovertemplate:'%{{text}}<extra></extra>'}};
  const shapes=[]; if(Number.isFinite(gx)&&Number.isFinite(gy)){{[[xRange[0],gx,gy,yRange[1],true,true],[gx,xRange[1],gy,yRange[1],false,true],[xRange[0],gx,yRange[0],gy,true,false],[gx,xRange[1],yRange[0],gy,false,false]].forEach(([x0,x1,y0,y1,xLower,yHigher])=>{{const good=Number(xLower)+Number(yHigher);const fillcolor=good===2?'rgba(34,197,94,0.14)':good===0?'rgba(239,68,68,0.14)':'rgba(234,179,8,0.14)';shapes.push({{type:'rect',x0,x1,y0,y1,layer:'below',fillcolor,line:{{width:0}}}});}});shapes.push({{type:'line',x0:gx,x1:gx,y0:0,y1:1,yref:'paper',layer:'below',line:{{color:'rgba(96,165,250,0.55)',width:2}}}});shapes.push({{type:'line',x0:0,x1:1,xref:'paper',y0:gy,y1:gy,layer:'below',line:{{color:'rgba(96,165,250,0.55)',width:2}}}});}}
  Plotly.react('chart',[trace],{{xaxis:{{tickformat:'.1f',ticksuffix:' ms',range:xRange,zeroline:false,showgrid:true,gridcolor:'rgba(71,85,105,0.35)',tickfont:{{color:'#cbd5e1',size:14}}}},yaxis:{{tickformat:'.3%',range:yRange,zeroline:false,showgrid:true,gridcolor:'rgba(71,85,105,0.35)',tickfont:{{color:'#cbd5e1',size:14}}}},autosize:true,hovermode:'closest',shapes,margin:{{l:80,r:30,t:45,b:55}},legend:{{orientation:'h',x:0,y:1.12,xanchor:'left',yanchor:'bottom',font:{{color:'#cbd5e1'}}}},paper_bgcolor:'#111827',plot_bgcolor:'#0b1120',font:{{color:'#cbd5e1'}}}},{{responsive:true,displaylogo:false}}).then(()=>{{const chart=document.getElementById('chart');if(chart.campaignClickHandler)chart.removeListener?.('plotly_click',chart.campaignClickHandler);chart.campaignClickHandler=event=>{{const target=event.points?.[0]?.customdata;if(validCommitUrl(target))window.open(target,'_blank','noopener,noreferrer');}};chart.on('plotly_click',chart.campaignClickHandler);}});
}}
let resizeTimer; window.addEventListener('resize',()=>{{clearTimeout(resizeTimer);resizeTimer=setTimeout(renderChart,120);}}); renderChart();
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--deployed-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plotly-src", default=PLOTLY_SCRIPT_URL)
    parser.add_argument("--review-mode", action="store_true")
    args = parser.parse_args()
    status = json.loads(args.status.read_text(encoding="utf-8"))
    output = render(
        status,
        deployed_commit=args.deployed_commit,
        plotly_src=args.plotly_src,
        review_mode=args.review_mode,
        completion_times=_completion_times(status, args.deployed_commit, PROJECT_ROOT),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"wrote trusted active campaign dashboard: {args.output}")
    print(f"deployed campaign commit: {args.deployed_commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
