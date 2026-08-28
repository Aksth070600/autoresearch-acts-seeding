import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "orchestration-files"))

from evaluate import build_timed_comparison  # noqa: E402
from objectives import (  # noqa: E402
    PRIMARY_EFFICIENCY_METRIC,
    PRIMARY_TIME_METRIC,
    add_run_metrics,
    choose_baseline,
    improved_over_baseline,
    pareto_front,
    time_first_key,
)


class PrimaryObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "candidate": "Genesis",
            "record": "Development/Genesis",
            "metrics": {
                "timed_seeding_time_per_event_ms": 100.0,
                "timed_total_time_per_event_ms": 300.0,
                "timed_ambiguity_particle_efficiency": 0.95,
                "timed_seeding_particle_efficiency": 0.80,
                "timed_ckf_particle_efficiency": 0.80,
            },
        }

    def test_total_time_winner_with_slower_seeding_is_not_recommended(self) -> None:
        diagnostic_winner = {
            "candidate": "DiagnosticWinner",
            "record": "Development/DiagnosticWinner",
            "metrics": {
                "timed_seeding_time_per_event_ms": 110.0,
                "timed_total_time_per_event_ms": 290.0,
                "timed_ambiguity_particle_efficiency": 0.94,
                "timed_seeding_particle_efficiency": 0.99,
                "timed_ckf_particle_efficiency": 0.99,
            },
        }

        self.assertFalse(improved_over_baseline(diagnostic_winner, self.baseline, "timed"))

    def test_objectives_are_only_the_two_primary_metrics(self) -> None:
        self.assertEqual(
            {PRIMARY_TIME_METRIC, PRIMARY_EFFICIENCY_METRIC},
            {"seeding_time_per_event_ms", "ambiguity_particle_efficiency"},
        )

    def test_record_loading_keeps_full_chain_as_diagnostic(self) -> None:
        metrics = {}
        add_run_metrics(
            metrics,
            "timed",
            {
                "timing_total": {"time_per_event_ms": 300.0},
                "timing": {"seeding": {"time_per_event_ms": 100.0}},
                "performance": {
                    "seeding": {"efficiency_particles": 0.99},
                    "ckf": {"efficiency_particles": 0.99},
                    "ambiguity_resolution": {
                        "efficiency_particles": 0.95,
                        "efficiency_tracks": 0.60,
                    },
                },
            },
        )

        self.assertEqual(
            metrics,
            {
                "timed_total_time_per_event_ms": 300.0,
                "timed_seeding_time_per_event_ms": 100.0,
                "timed_ambiguity_particle_efficiency": 0.95,
            },
        )

    def test_timed_comparison_reports_the_median_and_keeps_repetitions(self) -> None:
        stages = [
            {
                "comparison": "timed",
                "repetition": repetition,
                "name": f"timed-{repetition}",
                "events": 10,
                "status": "passed",
                "run_metrics": {
                    "timing_total": {"time_per_event_ms": float(value)},
                    "performance": {
                        "ambiguity_resolution": {"efficiency_particles": value / 100.0}
                    },
                },
            }
            for repetition, value in enumerate((120, 100, 110), start=1)
        ]

        comparison = build_timed_comparison(stages)
        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertTrue(comparison["complete"])
        self.assertEqual(comparison["repetition_count"], 3)
        self.assertEqual(len(comparison["repetitions"]), 3)
        self.assertEqual(comparison["median_run_metrics"]["timing_total"]["time_per_event_ms"], 110)
        self.assertEqual(
            comparison["median_run_metrics"]["performance"]["ambiguity_resolution"]["efficiency_particles"],
            1.1,
        )
        self.assertEqual(
            comparison["range_run_metrics"]["timing_total"]["time_per_event_ms"],
            20.0,
        )
        self.assertEqual(
            comparison["median_absolute_deviation_run_metrics"]["timing_total"][
                "time_per_event_ms"
            ],
            10.0,
        )

    def test_latest_complete_genesis_is_the_baseline(self) -> None:
        older = {
            "candidate": "Genesis",
            "category": "Development",
            "record": "Development/20260826T120000000000Z-Genesis/summary.json",
            "is_baseline": True,
            "status": "passed",
            "started_at": "2026-08-26T12:00:00+00:00",
            "metrics": self.baseline["metrics"],
        }
        newer = {
            **older,
            "record": "Development/20260826T130000000000Z-Genesis/summary.json",
            "started_at": "2026-08-26T13:00:00+00:00",
            "metrics": {
                **self.baseline["metrics"],
                "timed_seeding_time_per_event_ms": 90.0,
                "timed_total_time_per_event_ms": 290.0,
            },
        }
        incomplete = {
            **newer,
            "record": "Development/20260826T140000000000Z-Genesis/summary.json",
            "status": "failed",
            "started_at": "2026-08-26T14:00:00+00:00",
        }

        selected = choose_baseline([older, newer, incomplete], "Genesis")

        self.assertIs(selected, newer)

    def test_primary_tradeoffs_remain_on_the_pareto_front(self) -> None:
        faster = {
            "candidate": "Faster",
            "record": "Development/Faster",
            "metrics": {
                "timed_seeding_time_per_event_ms": 90.0,
                "timed_total_time_per_event_ms": 290.0,
                "timed_ambiguity_particle_efficiency": 0.94,
            },
        }
        more_efficient = {
            "candidate": "MoreEfficient",
            "record": "Development/MoreEfficient",
            "metrics": {
                "timed_seeding_time_per_event_ms": 110.0,
                "timed_total_time_per_event_ms": 310.0,
                "timed_ambiguity_particle_efficiency": 0.96,
            },
        }

        front = pareto_front([self.baseline, faster, more_efficient], "timed")
        self.assertEqual(
            {row["candidate"] for row in front},
            {"Genesis", "Faster", "MoreEfficient"},
        )
        self.assertEqual(front, sorted(front, key=time_first_key))


if __name__ == "__main__":
    unittest.main()
