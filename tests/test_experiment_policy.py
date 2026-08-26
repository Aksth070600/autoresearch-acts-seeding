import unittest
from pathlib import Path


POLICY = Path(__file__).parents[1] / "agent-instructions.md"


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


if __name__ == "__main__":
    unittest.main()
