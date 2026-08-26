"""Shared identity and constants for the controlled ACTS campaign protocol."""

from __future__ import annotations

from typing import Any


PROTOCOL_ID = "acts-seeding-v2"

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
    "development_events": 10,
    "evaluation_events": 50,
    "timed_repetitions": 3,
    "timed_aggregation": "median",
    "expected_unmasked_fpe_handling": "accept only after every requested event completed",
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


def protocol_events(mode: str) -> int:
    """Return the controlled event count for an evaluator mode."""

    if mode == "development":
        return int(PROTOCOL_METADATA["development_events"])
    if mode == "evaluation":
        return int(PROTOCOL_METADATA["evaluation_events"])
    raise ValueError(f"unsupported protocol mode: {mode}")
