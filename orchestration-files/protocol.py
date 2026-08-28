"""Shared identity and constants for the controlled ACTS campaign protocol."""

from __future__ import annotations

from typing import Any


PROTOCOL_ID = "acts-seeding-v3"

# Changing any controlled value requires a new protocol identity.  Keep this
# object JSON-compatible because it is embedded verbatim in every summary.
PROTOCOL_METADATA: dict[str, Any] = {
    "id": PROTOCOL_ID,
    "acts_version": "v46.5.0",
    "dataset": "ttbar_pu200",
    "execution_target": "HEPP02",
    "threads": 1,
    "seed": 42,
    "pileup": 200,
    "execution_stage": "seeding",
    "smoke_events": 1,
    "timing_events": 10,
    "rss_events": 10,
    "timed_repetitions": 3,
    "timed_aggregation": "median",
    "smoke_instrumentation": "none",
    "timing_instrumentation": "none",
    "rss_metrics_mode": "time",
    "rss_instrumentation": "GNU time -v",
    "expected_unmasked_fpe_handling": "accept only after every requested event completed",
}

# Known historical protocols remain available only for isolated read-only reports.
# Keep newest first so an empty active report can choose the newest archive with data.
HISTORICAL_PROTOCOLS: tuple[dict[str, Any], ...] = (
    {
        "id": "acts-seeding-v2",
        "acts_version": "v46.5.0",
        "dataset": "ttbar_pu200",
        "execution_target": "HEPP02",
        "threads": 1,
        "seed": 42,
        "pileup": 200,
        "development_events": 10,
        "evaluation_events": 50,
        "timed_repetitions": 3,
        "timed_aggregation": "median",
        "expected_unmasked_fpe_handling": "accept only after every requested event completed",
    },
)

# Campaign composition does not change scientific protocol compatibility.
# CAMPAIGN_COMPOSITION remains the owner of archived fixed-20 evidence.
CAMPAIGN_COMPOSITION: dict[str, int] = {
    "completed_candidates": 20,
    "major_candidates": 10,
    "minor_candidates": 5,
    "combination_candidates": 5,
}
# Continuous campaigns use this ratio without a fixed candidate total. Their
# graceful final count is any positive integer multiple of these values.
CONTINUOUS_CAMPAIGN_RATIO: dict[str, int] = {
    "major": 2,
    "minor": 1,
    "combination": 1,
}
CONTINUOUS_CAMPAIGN_PERCENTAGES: dict[str, int] = {
    category: value * 100 // sum(CONTINUOUS_CAMPAIGN_RATIO.values())
    for category, value in CONTINUOUS_CAMPAIGN_RATIO.items()
}
SOURCE_GROUNDED_MAJOR_MINIMUM = 3

# Reporting evidence only. This does not alter protocol compatibility,
# Development selection, or authority to run Evaluation.
EVALUATION_TIMING_REPORTING: dict[str, Any] = {
    "dispersion": "unscaled median absolute deviation",
    "practical_margin": "maximum Genesis repetition range or unscaled MAD",
    "classifications": ["confirmed", "directional", "inconclusive"],
}


def current_protocol() -> dict[str, Any]:
    """Return a copy suitable for embedding in a summary or report."""

    return dict(PROTOCOL_METADATA)


def is_compatible_summary(summary: dict[str, Any]) -> bool:
    """Return whether a summary belongs to the active controlled protocol."""

    return (
        summary.get("protocol_id") == PROTOCOL_ID
        and summary.get("protocol") == PROTOCOL_METADATA
    )


def is_complete_stage_matrix(stages: Any) -> bool:
    """Return whether stage evidence matches the exact seeding-only 1 + 3 + 1 matrix."""

    if not isinstance(stages, list) or len(stages) != 5:
        return False
    expected = [
        (
            "smoke",
            PROTOCOL_METADATA["smoke_events"],
            PROTOCOL_METADATA["execution_stage"],
            PROTOCOL_METADATA["smoke_instrumentation"],
            None,
        ),
        *[
            (
                "timed",
                PROTOCOL_METADATA["timing_events"],
                PROTOCOL_METADATA["execution_stage"],
                PROTOCOL_METADATA["timing_instrumentation"],
                repetition,
            )
            for repetition in range(
                1, int(PROTOCOL_METADATA["timed_repetitions"]) + 1
            )
        ],
        (
            "rss",
            PROTOCOL_METADATA["rss_events"],
            PROTOCOL_METADATA["execution_stage"],
            PROTOCOL_METADATA["rss_metrics_mode"],
            None,
        ),
    ]
    actual = [
        (
            stage.get("comparison"),
            stage.get("events"),
            stage.get("stage"),
            stage.get("metrics_mode"),
            stage.get("repetition"),
        )
        if isinstance(stage, dict) and stage.get("status") == "passed"
        else None
        for stage in stages
    ]
    return actual == expected


def is_complete_rss_evidence(value: Any) -> bool:
    """Return whether the separate instrumented run owns valid Peak RSS evidence."""

    if not isinstance(value, dict):
        return False
    peak_rss = value.get("resource_metrics", {}).get("peak_rss_kb")
    return (
        value.get("complete") is True
        and value.get("events") == PROTOCOL_METADATA["rss_events"]
        and value.get("stage") == PROTOCOL_METADATA["execution_stage"]
        and value.get("metrics_mode") == PROTOCOL_METADATA["rss_metrics_mode"]
        and value.get("status") == "passed"
        and isinstance(peak_rss, (int, float))
        and not isinstance(peak_rss, bool)
        and peak_rss >= 0
    )


def is_readable_summary(summary: dict[str, Any]) -> bool:
    """Accept current evidence and known v2 evidence for read-only historical access."""

    return is_compatible_summary(summary) or (
        summary.get("protocol_id") == "acts-seeding-v2"
        and isinstance(summary.get("protocol"), dict)
        and summary["protocol"].get("id") == "acts-seeding-v2"
    )


def protocol_events(stage: str) -> int:
    """Return the event count for one stage in the controlled 1 + 3 + 1 matrix."""

    fields = {
        "smoke": "smoke_events",
        "timing": "timing_events",
        "rss": "rss_events",
    }
    try:
        return int(PROTOCOL_METADATA[fields[stage]])
    except KeyError as error:
        raise ValueError(f"unsupported protocol stage: {stage}") from error
