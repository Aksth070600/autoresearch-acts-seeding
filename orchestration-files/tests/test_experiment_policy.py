import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY = PROJECT_ROOT / "agent-instructions.md"


class ExperimentPolicyTests(unittest.TestCase):
    def test_policy_requires_exact_composition_and_development_only_runs(self) -> None:
        text = POLICY.read_text(encoding="utf-8")
        lowered = " ".join(text.lower().split())

        self.assertIn("captain-controlled", lowered)
        self.assertIn("evaluation workloads are captain-controlled", lowered)
        self.assertIn("experiment candidates use the 10-event development workload only", lowered)
        self.assertIn("exactly 20 unique candidate experiments", lowered)
        self.assertIn("10 `major` candidates", lowered)
        self.assertIn("5 `minor` candidates", lowered)
        self.assertIn("5 `combination` candidates", lowered)
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
            "compatibility",
            "interaction hypothesis",
        ):
            self.assertIn(phrase, lowered)
        self.assertIn("make evaluate candidate=<candidate-name>", lowered)
        self.assertNotIn("evaluation=1", lowered)

    def test_protocol_owns_the_standard_composition(self) -> None:
        import sys

        sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))
        from protocol import CAMPAIGN_COMPOSITION

        self.assertEqual(
            CAMPAIGN_COMPOSITION,
            {
                "completed_candidates": 20,
                "major_candidates": 10,
                "minor_candidates": 5,
                "combination_candidates": 5,
            },
        )

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
