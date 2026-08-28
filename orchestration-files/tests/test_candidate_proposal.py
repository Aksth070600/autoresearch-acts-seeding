import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from evaluate import EvaluationError, load_candidate_proposal  # noqa: E402
from proposal import (  # noqa: E402
    ProposalError,
    bind_proposal,
    proposal_from_summary,
    proposal_hash,
)


class CandidateProposalTests(unittest.TestCase):
    commit = "a" * 40
    candidate = "BoundCandidate"
    intended_file = "optimization-files/Core/src/Seeding2/TripletSeeder.cpp"

    def proposal(self) -> dict:
        return {
            "schema_version": "1.0.0",
            "candidate": self.candidate,
            "implementation_commit": self.commit,
            "hypothesis": "A bounded traversal should reduce repeated work.",
            "falsifier": "Seeding time does not decrease or efficiency decreases.",
            "predicted_directions": {
                "timed_seeding_time_per_event_ms": "decrease",
                "timed_seeding_particle_efficiency": "unchanged",
            },
            "expected_hot_path": "Acts::TripletSeeder::createSeedsForGroup traversal.",
            "changed_symbols": ["Acts::TripletSeeder::createSeedsForGroup"],
            "intended_files": [self.intended_file],
            "novelty_reason": "No earlier candidate bounded this traversal.",
            "source_references": [
                {
                    "source_type": "Genesis",
                    "reference": "records/Development/Genesis/summary.json",
                    "relevance": "The baseline identifies the timing target.",
                    "directly_inspected": True,
                }
            ],
            "combination_provenance": None,
        }

    def campaign_input(self, proposal: dict | None) -> dict:
        metadata = {
            "candidate": self.candidate,
            "mechanism_key": "bounded-traversal",
            "mechanism_family": "traversal",
            "classification": "major",
        }
        if proposal is not None:
            metadata["proposal"] = proposal
        return {"attempt_metadata": [metadata]}

    def load(self, state: dict):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "campaign.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            return load_candidate_proposal(
                path, self.candidate, self.commit, [self.intended_file]
            )

    def test_evaluator_requires_proposal_and_matching_candidate(self) -> None:
        with self.assertRaisesRegex(EvaluationError, "proposal is required"):
            self.load(self.campaign_input(None))

        wrong = self.proposal()
        wrong["candidate"] = "OtherCandidate"
        with self.assertRaisesRegex(EvaluationError, "candidate does not match"):
            self.load(self.campaign_input(wrong))

    def test_evaluator_rejects_wrong_implementation_commit_and_files(self) -> None:
        wrong_commit = self.proposal()
        wrong_commit["implementation_commit"] = "b" * 40
        with self.assertRaisesRegex(EvaluationError, "commit does not match"):
            self.load(self.campaign_input(wrong_commit))

        with self.assertRaisesRegex(EvaluationError, "intended_files"):
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "campaign.json"
                path.write_text(
                    json.dumps(self.campaign_input(self.proposal())), encoding="utf-8"
                )
                load_candidate_proposal(
                    path,
                    self.candidate,
                    self.commit,
                    ["optimization-files/Core/src/Seeding2/Other.cpp"],
                )

    def test_hash_is_deterministic_and_hash_mismatch_is_rejected(self) -> None:
        proposal = self.proposal()
        reordered = {key: proposal[key] for key in reversed(proposal)}
        self.assertEqual(
            proposal_hash(proposal, self.commit),
            proposal_hash(reordered, self.commit),
        )
        binding = bind_proposal(proposal, self.candidate, self.commit)
        summary = {
            "candidate_name": self.candidate,
            "implementation_commit": self.commit,
            "proposal_binding": binding,
            "combination_provenance": None,
        }
        tampered = copy.deepcopy(summary)
        tampered["proposal_binding"]["proposal_hash"] = "0" * 64
        with self.assertRaisesRegex(ProposalError, "hash does not match"):
            proposal_from_summary(tampered)

    def test_summary_round_trip_preserves_exact_normalized_proposal(self) -> None:
        binding, identity = self.load(self.campaign_input(self.proposal()))
        summary = {
            "candidate_name": self.candidate,
            "implementation_commit": self.commit,
            "proposal_binding": binding,
            "combination_provenance": None,
        }
        self.assertEqual(proposal_from_summary(summary), binding["proposal"])
        self.assertEqual(identity["mechanism_key"], "bounded-traversal")


if __name__ == "__main__":
    unittest.main()
