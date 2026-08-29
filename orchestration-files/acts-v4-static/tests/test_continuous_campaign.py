import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC_MODULE = PROJECT_ROOT / "orchestration-files" / "acts-v4-static"
ORCHESTRATION = PROJECT_ROOT / "orchestration-files"
sys.path.insert(0, str(STATIC_MODULE))
sys.path.insert(0, str(ORCHESTRATION))

from continuous_campaign import (  # noqa: E402
    DATASET_ID,
    PLATFORM_COMMIT,
    SCIENTIFIC_GENESIS_COMMIT,
    build_status,
    completed_counts,
    consume_stop,
    finalization_blockers,
    next_category,
    observe_stop,
    validate_state,
)
from campaign_control import issue_body  # noqa: E402
from campaign_status import build_status as build_v3_status  # noqa: E402
from campaign_status import validate_live_state as validate_v3_live_state  # noqa: E402


UTC = timezone.utc
NOW = datetime(2026, 8, 29, 21, tzinfo=UTC)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class StaticV4ContinuousCampaignTests(unittest.TestCase):
    def state(self):
        return {
            "schema": "acts-v4-owned-static-continuous-campaign-v1",
            "campaign": {
                "name": "Owned static v4 continuous test",
                "branch": "fm/acts-v4-continuous-test",
                "campaign_id": "acts-v4-owned-static-20260829-test",
                "control_id": "c" * 64,
                "started_at": "2026-08-29T20:00:00Z",
                "platform_commit": PLATFORM_COMMIT,
                "scientific_genesis_commit": SCIENTIFIC_GENESIS_COMMIT,
                "acts_commit": "34edd48852f766e1b9d94d3dc996e27476339f1b",
                "protocol_id": "acts-seeding-v4-owned-static",
                "protocol_revision": 2,
                "dataset_id": DATASET_ID,
                "development_only": True,
                "evaluation_authorized": False,
            },
            "dataset": {
                "publication_path": f"/storage/thomaaks/acts-v4-owned-static/{DATASET_ID}",
                "manifest_sha256": "13274b01178462f1375eebd0cba283551a5ca04ec9724aa189aaf33e4e2f5666",
                "payload_sha256": "534c14c0cbc2f37aecd091d879c168348d2c2e2cc4f9719c3580bbd54dc6d510",
                "qualification_evidence_sha256": "ed16fef43f1b6818e52cf6b0493d9c786a70444d212e7ab521eadd03d4b37237",
            },
            "calibration": None,
            "current_attempt": None,
            "attempts": [],
            "corrections": [],
            "control": {
                "state": "open",
                "request": None,
                "observed_at": None,
                "consumed_at": None,
                "completed_at": None,
            },
            "scheduler": {
                "state": "running",
                "final_targets": None,
                "blocker": None,
            },
            "pull_request_url": None,
            "restoration": None,
        }

    def record(self, slot, classification, *, status="passed"):
        candidate = f"Candidate{slot}"
        proposal = {
            "schema_version": "1.0.0",
            "candidate": candidate,
            "slot": slot,
            "classification": classification,
            "mechanism_key": f"static-v4-test-mechanism-{slot}",
            "mechanism_family": f"family-{slot}",
            "implementation_commit": f"{slot:040x}",
            "hypothesis": "A source-grounded mechanism changes the static seeding hot path.",
            "falsifier": "The exact fixed-data result does not move as predicted.",
            "predicted_directions": {
                "timed_seeding_time_per_event_ms": "decrease",
                "timed_seeding_particle_efficiency": "unchanged",
            },
            "expected_hot_path": "Acts::GridTriplet seeding traversal",
            "changed_symbols": ["Acts::CandidateSymbol"],
            "intended_files": [
                "optimization-files/Core/src/Seeding2/TripletSeeder.cpp"
            ],
            "physics_invariants": [
                "all 50 ordered event hashes and the truth denominator remain exact"
            ],
            "novelty_reason": "The mechanism key and causal change are new to static v4.",
            "source_references": [
                {
                    "source_type": "inspected source code",
                    "reference": "https://github.com/acts-project/acts/blob/34edd48852f766e1b9d94d3dc996e27476339f1b/Core/src/Seeding2/TripletSeeder.cpp",
                    "relevance": "The implementation owns the measured hot path.",
                    "directly_inspected": True,
                    "inspected_scope": "TripletSeeder candidate traversal",
                    "acts_mapping": "Acts::TripletSeeder::createSeedsForGroup",
                }
            ],
            "derives_from": None,
            "combination_provenance": None,
        }
        value = {
            "schema": "acts-v4-owned-static-development-record-v2",
            "protocol_id": "acts-seeding-v4-owned-static",
            "protocol_revision": 2,
            "dataset_id": DATASET_ID,
            "category": "Development",
            "status": status,
            "candidate_name": candidate,
            "baseline": False,
            "slot": slot,
            "classification": classification,
            "mechanism_key": proposal["mechanism_key"],
            "implementation_commit": proposal["implementation_commit"],
            "proposal": proposal,
            "proposal_sha256": hashlib.sha256(canonical(proposal)).hexdigest(),
            "scientific_processes": 1,
            "result": {
                "protocol_id": "acts-seeding-v4-owned-static",
                "protocol_revision": 2,
                "dataset_id": DATASET_ID,
                "events": 50,
                "threads": 1,
                "process_exit_status": 0,
                "fpe": {"observed_unmasked": 0},
                "input_event_hashes": [f"{index:064x}" for index in range(50)],
                "stats": {
                    "nTotalParticles": 58310,
                    "nTotalMatchedParticles": 57398,
                    "nTotalTracks": 1065071,
                    "nTotalMatchedTracks": 644305,
                    "nTotalFakeTracks": 26451,
                    "nTotalDuplicateTracks": 586907,
                },
                "timing": {
                    "per_event_nanoseconds": 295000000,
                    "total_nanoseconds": 14750000000,
                },
                "resources": {"wall_seconds": "77.0", "peak_rss_kb": 2120000},
                "loaded_acts_dso_closure": {"complete": True, "object_count": 33},
                "candidate_binding": {
                    "proposal_sha256": hashlib.sha256(canonical(proposal)).hexdigest()
                },
            },
            "scientific_classification": {"overall": "inconclusive"}
            if status == "passed"
            else None,
            "latency": {
                "preparation_seconds": "170.0",
                "build_seconds": "87.0",
                "record_preparation_seconds": "1.0",
                "queue_to_immutable_record_seconds": "249.0",
                "preparation_build_target_passed": False,
                "static_process_target_passed": True,
                "queue_to_record_target_passed": True,
            },
            "corrections": [],
        }
        value["record_sha256"] = hashlib.sha256(canonical(value)).hexdigest()
        return value

    def add_attempt(self, state, record, path):
        state["attempts"].append(
            {
                "slot": record["slot"],
                "candidate": record["candidate_name"],
                "classification": record["classification"],
                "mechanism_key": record["mechanism_key"],
                "implementation_commit": record["implementation_commit"],
                "proposal_path": f"orchestration-files/acts-v4-continuous/proposals/{record['slot']:04d}.json",
                "proposal_sha256": record["proposal_sha256"],
                "record_path": str(path),
                "record_sha256": record["record_sha256"],
                "state": "recorded",
                "scheduling": "ordinary",
            }
        )

    def test_v4_state_keeps_platform_and_scientific_genesis_distinct(self):
        state = validate_state(self.state())
        self.assertEqual(state["campaign"]["platform_commit"], PLATFORM_COMMIT)
        self.assertEqual(
            state["campaign"]["scientific_genesis_commit"], SCIENTIFIC_GENESIS_COMMIT
        )
        wrong = self.state()
        wrong["campaign"]["scientific_genesis_commit"] = PLATFORM_COMMIT
        with self.assertRaisesRegex(ValueError, "scientific Genesis"):
            validate_state(wrong)

    def test_scheduler_repeats_two_major_one_minor_one_combination_blocks(self):
        expected = ["major", "major", "minor", "combination"] * 3
        actual = []
        for completed in range(len(expected)):
            actual.append(
                next_category(completed, control_state="open", final_targets=None)
            )
        self.assertEqual(actual, expected)
        self.assertEqual(
            next_category(
                3,
                control_state="consumed",
                final_targets={"major": 2, "minor": 1, "combination": 1},
            ),
            "combination",
        )
        self.assertIsNone(
            next_category(
                4,
                control_state="consumed",
                final_targets={"major": 2, "minor": 1, "combination": 1},
            )
        )

    def test_records_are_exact_revision_two_static_v4_only_and_invalid_attempts_keep_slots(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = self.state()
            for slot, category, status in (
                (1, "major", "passed"),
                (2, "major", "invalid"),
                (3, "minor", "passed"),
                (4, "combination", "passed"),
            ):
                path = root / f"record-{slot}.json"
                record = self.record(slot, category, status=status)
                path.write_bytes(canonical(record))
                self.add_attempt(state, record, path)
            validated = validate_state(state, repository_root=PROJECT_ROOT)
            self.assertEqual(
                completed_counts(validated), {"major": 2, "minor": 1, "combination": 1}
            )
            snapshot = build_status(
                validated, NOW, "f" * 40, repository_root=PROJECT_ROOT
            )
            self.assertEqual(snapshot["composition"]["completed_blocks"], 1)
            self.assertEqual(snapshot["attempts"][1]["status"], "invalid")

            v3 = self.record(4, "combination")
            v3["protocol_id"] = "acts-seeding-v3"
            v3["record_sha256"] = hashlib.sha256(
                canonical({k: v for k, v in v3.items() if k != "record_sha256"})
            ).hexdigest()
            path = root / "wrong.json"
            path.write_bytes(canonical(v3))
            state["attempts"][3]["record_path"] = str(path)
            state["attempts"][3]["record_sha256"] = v3["record_sha256"]
            with self.assertRaisesRegex(ValueError, "revision-2 owned-static"):
                validate_state(state, repository_root=PROJECT_ROOT)

    def test_authenticated_stop_is_observed_then_consumed_to_current_block(self):
        state = self.state()
        payload = {
            "schema_version": "1.0.0",
            "campaign_id": state["campaign"]["campaign_id"],
            "campaign_branch": state["campaign"]["branch"],
            "control_id": state["campaign"]["control_id"],
            "requested_at": "2026-08-29T21:00:00Z",
            "requested_by": "captain",
            "workflow_run_id": 123,
            "workflow_run_attempt": 1,
            "workflow_run_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/actions/runs/123",
        }
        issue = {
            "number": 88,
            "title": "Finish continuous campaign: " + payload["campaign_id"],
            "body": issue_body(payload),
            "html_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/issues/88",
            "labels": [{"name": "campaign-control"}],
            "user": {"login": "github-actions[bot]"},
        }
        observed, changed = observe_stop(state, [issue], NOW)
        self.assertTrue(changed)
        self.assertEqual(observed["control"]["state"], "requested")
        consumed = consume_stop(observed, NOW)
        self.assertEqual(
            consumed["scheduler"]["final_targets"],
            {"major": 2, "minor": 1, "combination": 1},
        )
        self.assertEqual(consumed["control"]["state"], "consumed")

    def test_v3_control_snapshot_remains_v3_and_does_not_import_static_records(self):
        bridge = {
            "schema_version": "1.1.0",
            "campaign": {
                "name": "Static v4 control bridge",
                "branch": "fm/acts-v4-continuous-test",
                "phase": "See exact owned-static v4 sidecar",
                "started_at": "2026-08-29T20:00:00Z",
                "mode": "continuous",
                "campaign_id": "acts-v4-owned-static-20260829-test",
                "control_id": "c" * 64,
                "genesis_commit": PLATFORM_COMMIT,
                "targets": {
                    "major_percentage": 50,
                    "minor_percentage": 25,
                    "combination_percentage": 25,
                },
            },
            "current_attempt": None,
            "attempt_metadata": [],
            "blockers": [],
            "pull_request_url": None,
            "control": self.state()["control"],
            "scheduler": {
                "state": "running",
                "combination_readiness": None,
                "final_targets": None,
                "blocker": None,
            },
        }
        live = validate_v3_live_state(bridge)
        snapshot = build_v3_status(live, [], NOW, "f" * 40)
        self.assertEqual(snapshot["protocol_id"], "acts-seeding-v3")
        self.assertEqual(snapshot["progress"]["completed_candidates"], 0)

    def test_finalization_requires_consumed_stop_exact_block_and_genesis_restoration(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", root], check=True)
            subprocess.run(
                ["git", "-C", root, "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", root, "config", "user.name", "Test"], check=True
            )
            optimization = root / "optimization-files"
            optimization.mkdir()
            (optimization / "genesis.cpp").write_text("genesis\n", encoding="utf-8")
            subprocess.run(["git", "-C", root, "add", "."], check=True)
            subprocess.run(["git", "-C", root, "commit", "-qm", "Genesis"], check=True)
            genesis = subprocess.check_output(
                ["git", "-C", root, "rev-parse", "HEAD"], text=True
            ).strip()

            state = self.state()
            state["campaign"]["platform_commit"] = genesis
            state["campaign"]["scientific_genesis_commit"] = genesis
            state["campaign"]["started_at"] = "2026-08-29T20:00:00Z"
            state["control"].update(
                {
                    "state": "consumed",
                    "request": {
                        "issue_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/issues/88"
                    },
                    "observed_at": "2026-08-29T21:00:00Z",
                    "consumed_at": "2026-08-29T21:01:00Z",
                }
            )
            state["scheduler"].update(
                {
                    "state": "finishing",
                    "final_targets": {"major": 2, "minor": 1, "combination": 1},
                }
            )
            state["calibration"] = {
                "path": "calibration.json",
                "sha256": "a" * 64,
                "runs": 5,
                "valid": True,
            }
            state["restoration"] = {
                "validated": True,
                "evidence_path": "restoration.json",
                "evidence_sha256": "b" * 64,
            }
            self.assertTrue(
                any(
                    "exact final composition" in item
                    for item in finalization_blockers(state, root)
                )
            )
            (optimization / "genesis.cpp").write_text("candidate\n", encoding="utf-8")
            self.assertTrue(
                any(
                    "restored exactly" in item
                    for item in finalization_blockers(state, root)
                )
            )


if __name__ == "__main__":
    unittest.main()
