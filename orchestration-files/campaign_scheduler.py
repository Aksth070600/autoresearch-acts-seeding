"""Deterministic scheduling for continuous ACTS Development campaigns."""

from __future__ import annotations

import math
from typing import Any

from protocol import CONTINUOUS_CAMPAIGN_RATIO


CATEGORIES = ("major", "minor", "combination")
CATEGORY_COUNT_FIELDS = {
    "major": "major_candidates",
    "minor": "minor_candidates",
    "combination": "combination_candidates",
}


class SchedulerError(ValueError):
    """Raised when durable scheduler state is inconsistent."""


def normalize_counts(value: dict[str, Any]) -> dict[str, int]:
    """Return strict category counts in scheduler category names."""

    if not isinstance(value, dict):
        raise SchedulerError("candidate counts must be an object")
    counts: dict[str, int] = {}
    for category in CATEGORIES:
        field = CATEGORY_COUNT_FIELDS[category]
        count = value.get(category, value.get(field))
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise SchedulerError(f"{field} must be a non-negative integer")
        counts[category] = count
    return counts


def exact_ratio(counts: dict[str, Any], *, require_positive: bool = True) -> bool:
    """Return whether counts have the exact 2:1:1 retained-candidate ratio."""

    normalized = normalize_counts(counts)
    total = sum(normalized.values())
    return (
        (not require_positive or total > 0)
        and normalized["major"] == 2 * normalized["minor"]
        and normalized["minor"] == normalized["combination"]
    )


def minimal_final_targets(counts: dict[str, Any]) -> dict[str, int]:
    """Return the smallest positive 2:1:1 target that contains all counts."""

    normalized = normalize_counts(counts)
    units = max(
        1,
        math.ceil(normalized["major"] / CONTINUOUS_CAMPAIGN_RATIO["major"]),
        normalized["minor"],
        normalized["combination"],
    )
    targets = {
        category: units * CONTINUOUS_CAMPAIGN_RATIO[category] for category in CATEGORIES
    }
    return {
        "completed_candidates": sum(targets.values()),
        **{
            CATEGORY_COUNT_FIELDS[category]: targets[category]
            for category in CATEGORIES
        },
    }


def finalization_deficits(
    counts: dict[str, Any], targets: dict[str, Any]
) -> dict[str, int]:
    """Return remaining category counts for a persisted final target."""

    normalized = normalize_counts(counts)
    target_counts = normalize_counts(targets)
    if not exact_ratio(target_counts):
        raise SchedulerError("final targets must have a positive exact 2:1:1 ratio")
    deficits = {
        category: target_counts[category] - normalized[category]
        for category in CATEGORIES
    }
    if any(value < 0 for value in deficits.values()):
        raise SchedulerError("completed candidates exceed the persisted final target")
    expected_total = sum(target_counts.values())
    completed_target = targets.get("completed_candidates")
    if completed_target is not None and completed_target != expected_total:
        raise SchedulerError(
            "final target categories do not sum to completed_candidates"
        )
    return deficits


def composition_state(counts: dict[str, Any]) -> dict[str, dict[str, float | int]]:
    """Report completed percentages and quota deficits at the current total."""

    normalized = normalize_counts(counts)
    total = sum(normalized.values())
    ratio_total = sum(CONTINUOUS_CAMPAIGN_RATIO.values())
    result: dict[str, dict[str, float | int]] = {}
    for category in CATEGORIES:
        target_fraction = CONTINUOUS_CAMPAIGN_RATIO[category] / ratio_total
        completed = normalized[category]
        result[category] = {
            "completed": completed,
            "target_percentage": target_fraction * 100,
            "completed_percentage": completed / total * 100 if total else 0.0,
            "deficit_candidates": total * target_fraction - completed,
        }
    return result


def _priority_scores(counts: dict[str, int]) -> dict[str, float]:
    """Score the next slot by target deficit, with category order as tie-break."""

    next_total = sum(counts.values()) + 1
    ratio_total = sum(CONTINUOUS_CAMPAIGN_RATIO.values())
    return {
        category: (
            next_total * CONTINUOUS_CAMPAIGN_RATIO[category] / ratio_total
            - counts[category]
        )
        for category in CATEGORIES
    }


def choose_category(
    counts: dict[str, Any],
    *,
    combination_eligible: bool,
    allowed_deficits: dict[str, int] | None = None,
) -> str | None:
    """Choose the highest deterministic deficit without bypassing eligibility."""

    normalized = normalize_counts(counts)
    scores = _priority_scores(normalized)
    eligible = []
    for category in CATEGORIES:
        if category == "combination" and not combination_eligible:
            continue
        if allowed_deficits is not None and allowed_deficits.get(category, 0) <= 0:
            continue
        eligible.append(category)
    if not eligible:
        return None
    return max(
        eligible, key=lambda category: (scores[category], -CATEGORIES.index(category))
    )


def schedule_decision(
    counts: dict[str, Any],
    *,
    control_state: str,
    current_attempt: dict[str, Any] | None,
    combination_eligible: bool,
    final_targets: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the next safe-boundary action from durable campaign state."""

    normalized = normalize_counts(counts)
    if current_attempt is not None:
        state = current_attempt.get("state")
        purpose = current_attempt.get("scheduling", "ordinary")
        if control_state == "requested" and purpose == "ordinary" and state == "queued":
            return {
                "action": "cancel-queued",
                "category": None,
                "reason": "A stop request was observed before the queued ordinary candidate started.",
            }
        return {
            "action": "finish-active",
            "category": current_attempt.get("classification"),
            "reason": "Finish the active candidate transaction and record its restoration evidence.",
        }

    if control_state == "open":
        category = choose_category(
            normalized, combination_eligible=combination_eligible
        )
        return {
            "action": "schedule",
            "category": category,
            "reason": "Selected by deterministic target deficit and category-order tie-break.",
        }

    if control_state == "requested":
        return {
            "action": "consume-stop",
            "category": None,
            "final_targets": minimal_final_targets(normalized),
            "reason": "No candidate transaction is active; persist the smallest exact final target.",
        }

    if control_state == "consumed":
        if final_targets is None:
            raise SchedulerError(
                "a consumed stop request requires persisted final targets"
            )
        deficits = finalization_deficits(normalized, final_targets)
        if not any(deficits.values()):
            return {
                "action": "finalize",
                "category": None,
                "deficits": deficits,
                "reason": "Retained candidates have reached the persisted exact 2:1:1 target.",
            }
        category = choose_category(
            normalized,
            combination_eligible=combination_eligible,
            allowed_deficits=deficits,
        )
        if category is None:
            combination_needed = deficits["combination"] > 0
            reason = (
                "Finalization requires a combination candidate, but no validated compatible "
                "source set and provenance are available."
                if combination_needed
                else "No eligible category can satisfy the persisted finalization deficits."
            )
            return {
                "action": "blocked",
                "category": None,
                "deficits": deficits,
                "reason": reason,
            }
        return {
            "action": "schedule-finalization",
            "category": category,
            "deficits": deficits,
            "reason": "Selected from only the persisted exact-ratio category deficits.",
        }

    if control_state == "completed":
        return {
            "action": "complete",
            "category": None,
            "reason": "The completed campaign is immutable.",
        }
    raise SchedulerError(f"unsupported campaign control state: {control_state}")
