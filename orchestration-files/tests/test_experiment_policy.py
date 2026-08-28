import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY = PROJECT_ROOT / "agent-instructions.md"


class ExperimentPolicyTests(unittest.TestCase):
    def test_policy_requires_continuous_composition_and_development_only_runs(self) -> None:
        text = POLICY.read_text(encoding="utf-8")
        lowered = " ".join(text.lower().split())

        self.assertIn("captain-controlled", lowered)
        self.assertIn("evaluation remains captain-controlled", lowered)
        self.assertIn("experiment agents run development only", lowered)
        self.assertIn("protocol.py` owns the controlled evaluator contract", lowered)
        self.assertIn("use it without overrides", lowered)
        self.assertIn("judge complete development results by the two primary objectives", lowered)
        self.assertIn("captain-approved scientific interpretation", lowered)
        self.assertIn("complete v2 and v3 records share one evidence family", lowered)
        self.assertIn("never substitute v2 ambiguity efficiency", lowered)
        self.assertIn("approximate diagnostic only", lowered)
        self.assertIn("rss never affects selection", lowered)
        self.assertIn("accept expected unmasked fpes only when every requested event completed", lowered)
        self.assertIn("run a continuous development campaign", lowered)
        self.assertIn("no fixed total before its authenticated stop request", lowered)
        self.assertIn("largest 50/25/25 category deficit", lowered)
        self.assertIn("the candidate categories are disjoint", lowered)
        self.assertNotIn("a fixed standard campaign", lowered)
        self.assertIn("combination candidates do not count as major or minor", lowered)
        self.assertIn("no more than 3 consecutive", lowered)
        self.assertIn("restore the canonical genesis implementation", lowered)
        for phrase in (
            "algorithm, traversal, allocation, data-layout, pruning, search-bound, or data-flow",
            "mechanism_key",
            "mechanism_family",
            "changed_symbols",
            "expected_hot_path",
            "novelty_reason",
            "semantic duplicate",
            "source candidate names",
            "source mechanism keys",
            "full source implementation commits",
            "directly inspected",
            "compatible",
            "interaction hypothesis",
        ):
            self.assertIn(phrase, lowered)
        self.assertIn("make evaluate candidate=<candidate-name>", lowered)
        self.assertNotIn("evaluation=1", lowered)

    def test_protocol_owns_the_standard_composition(self) -> None:
        import sys

        sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))
        from protocol import (
            CAMPAIGN_COMPOSITION,
            PROTOCOL_ID,
            PROTOCOL_METADATA,
            SEEDING_OBJECTIVE_FAMILY_ID,
            SEEDING_OBJECTIVE_METRICS,
            V2_PROTOCOL_METADATA,
            seeding_objective_protocol,
        )

        self.assertEqual(PROTOCOL_ID, "acts-seeding-v3")
        self.assertEqual(PROTOCOL_METADATA["execution_stage"], "seeding")
        self.assertEqual(PROTOCOL_METADATA["smoke_events"], 1)
        self.assertEqual(PROTOCOL_METADATA["timing_events"], 10)
        self.assertEqual(PROTOCOL_METADATA["rss_events"], 10)
        self.assertEqual(PROTOCOL_METADATA["timing_instrumentation"], "none")
        self.assertEqual(PROTOCOL_METADATA["rss_metrics_mode"], "time")
        self.assertNotIn("evaluation_events", PROTOCOL_METADATA)
        self.assertEqual(
            SEEDING_OBJECTIVE_FAMILY_ID,
            "acts-seeding-v2-v3-seeding-objectives",
        )
        self.assertEqual(
            SEEDING_OBJECTIVE_METRICS,
            (
                "timed_seeding_time_per_event_ms",
                "timed_seeding_particle_efficiency",
            ),
        )
        self.assertEqual(
            seeding_objective_protocol(
                {
                    "protocol_id": "acts-seeding-v2",
                    "protocol": V2_PROTOCOL_METADATA,
                }
            ),
            V2_PROTOCOL_METADATA,
        )
        invalid_v2 = dict(V2_PROTOCOL_METADATA, threads=2)
        self.assertIsNone(
            seeding_objective_protocol(
                {"protocol_id": "acts-seeding-v2", "protocol": invalid_v2}
            )
        )
        self.assertEqual(
            CAMPAIGN_COMPOSITION,
            {
                "completed_candidates": 20,
                "major_candidates": 10,
                "minor_candidates": 5,
                "combination_candidates": 5,
            },
        )

    def test_report_workflow_defaults_to_seeding_efficiency(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "reports.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("default: timed_seeding_particle_efficiency", workflow)
        self.assertIn("Y_METRIC: ${{ inputs.y_metric || 'timed_seeding_particle_efficiency' }}", workflow)
        self.assertNotIn("default: timed_ambiguity_particle_efficiency", workflow)
        self.assertNotIn("timed_peak_rss_kb", workflow)
        self.assertNotIn("- rss_peak_rss_kb", workflow)
        self.assertIn("rss_genesis_offset_peak_rss_kb", workflow)

    def test_build_jobs_are_capped_and_forwarded_to_hepp02(self) -> None:
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        helper = (
            PROJECT_ROOT / "orchestration-files/HEPP-files/run-hepp-helper.sh"
        ).read_text(encoding="utf-8")
        build = (
            PROJECT_ROOT / "orchestration-files/HEPP-files/build.sh"
        ).read_text(encoding="utf-8")
        evaluator = (
            PROJECT_ROOT / "orchestration-files/evaluate.py"
        ).read_text(encoding="utf-8")

        self.assertIn("ACTS_BUILD_JOBS ?= 8", makefile)
        self.assertIn("ACTS_BUILD_JOBS='$(ACTS_BUILD_JOBS)' python3", makefile)
        self.assertIn('ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"', helper)
        self.assertIn("ACTS_BUILD_JOBS=$(printf '%q'", helper)
        self.assertIn('ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"', build)
        self.assertIn('echo "ACTS build parallel jobs: $ACTS_BUILD_JOBS"', build)
        self.assertNotIn("nproc", build)
        self.assertIn("require_capped_build_log(build)", evaluator)
        self.assertIn("require_capped_build_log(rebuild)", evaluator)
        self.assertIn('build_jobs != "8"', evaluator)


if __name__ == "__main__":
    unittest.main()
