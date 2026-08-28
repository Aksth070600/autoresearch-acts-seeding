import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY = PROJECT_ROOT / "agent-instructions.md"


class ExperimentPolicyTests(unittest.TestCase):
    def test_policy_requires_structural_search_and_development_only_runs(self) -> None:
        text = POLICY.read_text(encoding="utf-8")
        lowered = " ".join(text.lower().split())

        self.assertIn("captain-controlled", lowered)
        self.assertIn("evaluation workloads are captain-controlled", lowered)
        self.assertIn("experiment candidates use the 10-event development workload only", lowered)
        self.assertIn("at least 20 completed candidate attempts", lowered)
        self.assertIn("at least 10 structurally distinct", lowered)
        self.assertIn("no more than 5 micro-optimization", lowered)
        self.assertIn("no more than 3 consecutive", lowered)
        for phrase in (
            "algorithm or data flow",
            "traversal or control flow",
            "data layout or allocation behavior",
            "pruning or search bounds",
            "mechanism_key",
            "changed_symbols",
            "expected_hot_path",
            "novelty_reason",
            "semantic duplicate",
        ):
            self.assertIn(phrase, lowered)
        self.assertIn("make evaluate candidate=<candidate-name>", lowered)
        self.assertNotIn("evaluation=1", lowered)

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
