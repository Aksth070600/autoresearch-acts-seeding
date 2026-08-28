import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATION = PROJECT_ROOT / "orchestration-files"
spec = importlib.util.spec_from_file_location(
    "select_evaluation", ORCHESTRATION / "select-evaluation.py"
)
assert spec is not None and spec.loader is not None
select_evaluation = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ORCHESTRATION))
spec.loader.exec_module(select_evaluation)


class SelectEvaluationTests(unittest.TestCase):
    def test_selection_uses_seeding_time_not_full_chain_time(self) -> None:
        baseline = {
            "candidate": "Genesis",
            "category": "Development",
            "record": "Development/Genesis/summary.json",
            "commit": "genesis",
            "is_baseline": True,
            "status": "passed",
            "started_at": "2026-08-26T12:00:00+00:00",
            "metrics": {
                "timed_seeding_time_per_event_ms": 100.0,
                "timed_total_time_per_event_ms": 300.0,
                "timed_ambiguity_particle_efficiency": 0.95,
            },
        }
        faster_full_chain = {
            **baseline,
            "candidate": "FasterFullChain",
            "record": "Development/FasterFullChain/summary.json",
            "commit": "faster-full-chain",
            "is_baseline": False,
            "metrics": {
                "timed_seeding_time_per_event_ms": 110.0,
                "timed_total_time_per_event_ms": 250.0,
                "timed_ambiguity_particle_efficiency": 0.95,
            },
        }
        slower_full_chain = {
            **baseline,
            "candidate": "FasterSeeding",
            "record": "Development/FasterSeeding/summary.json",
            "commit": "faster-seeding",
            "is_baseline": False,
            "metrics": {
                "timed_seeding_time_per_event_ms": 90.0,
                "timed_total_time_per_event_ms": 350.0,
                "timed_ambiguity_particle_efficiency": 0.95,
            },
        }

        candidates = [faster_full_chain, slower_full_chain]
        self.assertEqual(
            [row["candidate"] for row in select_evaluation.rank_seeding_time(candidates)],
            ["FasterSeeding", "FasterFullChain"],
        )
        selected = select_evaluation.choose([baseline, *candidates], "Genesis", 1)

        self.assertEqual([row["candidate"] for row in selected], ["Genesis", "FasterSeeding"])
        self.assertEqual(
            selected[1]["selection_reason"], "highest timed particle ambiguity efficiency"
        )


if __name__ == "__main__":
    unittest.main()
