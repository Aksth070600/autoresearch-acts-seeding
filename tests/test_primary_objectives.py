import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "orchestration-files"))

from evaluate import build_timed_comparison  # noqa: E402
from evolution import (  # noqa: E402
    PRIMARY_EFFICIENCY_METRIC,
    PRIMARY_TIME_METRIC,
    candidate_pool,
    improved_over_baseline,
    objective_vector,
    pareto_front,
    recommendation,
)


class PrimaryObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = {
            "candidate": "Genesis",
            "record": "Development/Genesis",
            "metrics": {
                "timed_total_time_per_event_ms": 100.0,
                "timed_ambiguity_particle_efficiency": 0.95,
                "timed_seeding_particle_efficiency": 0.80,
                "timed_ckf_particle_efficiency": 0.80,
            },
        }

    def test_diagnostic_winner_with_worse_primary_metrics_is_not_recommended(self) -> None:
        diagnostic_winner = {
            "candidate": "DiagnosticWinner",
            "record": "Development/DiagnosticWinner",
            "metrics": {
                "timed_total_time_per_event_ms": 110.0,
                "timed_ambiguity_particle_efficiency": 0.94,
                "timed_seeding_particle_efficiency": 0.99,
                "timed_ckf_particle_efficiency": 0.99,
            },
        }

        self.assertFalse(improved_over_baseline(diagnostic_winner, self.baseline, "timed"))
        pool = candidate_pool([diagnostic_winner], self.baseline, "timed")
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["candidate"], "Genesis")
        self.assertIs(
            recommendation([self.baseline, diagnostic_winner], self.baseline, "timed"),
            self.baseline,
        )

    def test_objectives_are_only_the_two_primary_metrics(self) -> None:
        vector = objective_vector(self.baseline, "timed")
        self.assertEqual(vector, [100.0, -0.95])
        self.assertEqual(len(vector), 2)
        self.assertEqual(
            {PRIMARY_TIME_METRIC, PRIMARY_EFFICIENCY_METRIC},
            {"total_time_per_event_ms", "ambiguity_particle_efficiency"},
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

    def test_primary_tradeoffs_remain_on_the_pareto_front(self) -> None:
        faster = {
            "candidate": "Faster",
            "record": "Development/Faster",
            "metrics": {
                "timed_total_time_per_event_ms": 90.0,
                "timed_ambiguity_particle_efficiency": 0.94,
            },
        }
        more_efficient = {
            "candidate": "MoreEfficient",
            "record": "Development/MoreEfficient",
            "metrics": {
                "timed_total_time_per_event_ms": 110.0,
                "timed_ambiguity_particle_efficiency": 0.96,
            },
        }

        front = pareto_front([self.baseline, faster, more_efficient], "timed")
        self.assertEqual(
            {row["candidate"] for row in front},
            {"Genesis", "Faster", "MoreEfficient"},
        )


if __name__ == "__main__":
    unittest.main()
