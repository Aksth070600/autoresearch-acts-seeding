import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from campaign_control import (  # noqa: E402
    CONTROL_LABEL,
    CONTROL_TITLE_PREFIX,
    ControlError,
    consume_stop_request,
    finalization_blockers,
    issue_body,
    observe_stop_request,
    request_stop,
)
from campaign_scheduler import (  # noqa: E402
    choose_category,
    exact_ratio,
    finalization_deficits,
    minimal_final_targets,
    schedule_decision,
)
from campaign_status import (  # noqa: E402
    build_status,
    validate_live_state,
    validate_status,
)
from evaluate import EvaluationError, enforce_continuous_development_run  # noqa: E402
from visualizations.campaign import render  # noqa: E402


UTC = timezone.utc
NOW = datetime(2026, 9, 1, 10, tzinfo=UTC)


class FakeForge:
    def __init__(self, snapshot=None, pulls=None, issues=None):
        self.snapshot = snapshot
        self.pulls = pulls or []
        self.issues = issues or []
        self.created = []
        self.label_ensured = False

    def get_campaign_snapshot(self, branch):
        if self.snapshot is None:
            raise RuntimeError("not found")
        return copy.deepcopy(self.snapshot)

    def open_campaign_pulls(self, branch):
        return copy.deepcopy(self.pulls)

    def control_issues(self):
        return copy.deepcopy(self.issues)

    def ensure_control_label(self):
        self.label_ensured = True

    def create_control_issue(self, title, body):
        issue = {
            "number": 71,
            "title": title,
            "body": body,
            "html_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/issues/71",
            "labels": [{"name": CONTROL_LABEL}],
            "user": {"login": "github-actions[bot]"},
        }
        self.created.append(issue)
        self.issues.append(issue)
        return copy.deepcopy(issue)


class ContinuousCampaignTests(unittest.TestCase):
    def raw_state(self, *, current=None, control=None, scheduler=None):
        return {
            "schema_version": "1.1.0",
            "campaign": {
                "name": "Continuous test",
                "branch": "autoresearch-acts-seeding/continuous-test",
                "phase": "continuous Development",
                "started_at": "2026-09-01T09:00:00Z",
                "mode": "continuous",
                "campaign_id": "continuous-test-20260901",
                "control_id": "c" * 64,
                "genesis_commit": "a" * 40,
                "targets": {
                    "major_percentage": 50,
                    "minor_percentage": 25,
                    "combination_percentage": 25,
                },
            },
            "current_attempt": current,
            "attempt_metadata": [],
            "blockers": [],
            "pull_request_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/pull/70",
            "control": control
            or {
                "state": "open",
                "request": None,
                "observed_at": None,
                "consumed_at": None,
                "completed_at": None,
            },
            "scheduler": scheduler
            or {
                "state": "running",
                "combination_readiness": None,
                "final_targets": None,
                "blocker": None,
            },
        }

    def snapshot(self, raw=None):
        state = validate_live_state(raw or self.raw_state())
        snapshot = build_status(state, [], NOW, "b" * 40)
        validate_status(snapshot)
        return snapshot

    def pull(self):
        branch = self.raw_state()["campaign"]["branch"]
        return {
            "html_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/pull/70",
            "head": {
                "ref": branch,
                "repo": {"full_name": "Aksth070600/autoresearch-acts-seeding"},
            },
        }

    def context(self, run_id=900):
        return {"actor": "captain", "run_id": run_id, "run_attempt": 1}

    def durable_issue(self, *, control_id=None, campaign_id=None, run_id=900):
        campaign = self.raw_state()["campaign"]
        payload = {
            "schema_version": "1.0.0",
            "campaign_id": campaign_id or campaign["campaign_id"],
            "campaign_branch": campaign["branch"],
            "control_id": control_id or campaign["control_id"],
            "requested_at": "2026-09-01T10:00:00Z",
            "requested_by": "captain",
            "workflow_run_id": run_id,
            "workflow_run_attempt": 1,
            "workflow_run_url": f"https://github.com/Aksth070600/autoresearch-acts-seeding/actions/runs/{run_id}",
        }
        return {
            "number": 71,
            "title": CONTROL_TITLE_PREFIX + payload["campaign_id"],
            "body": issue_body(payload),
            "html_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/issues/71",
            "labels": [{"name": CONTROL_LABEL}],
            "user": {"login": "github-actions[bot]"},
        }

    def test_deterministic_deficit_schedule_and_tie_break(self):
        counts = {"major": 0, "minor": 0, "combination": 0}
        sequence = []
        for _ in range(8):
            category = choose_category(counts, combination_eligible=True)
            sequence.append(category)
            counts[category] += 1
        self.assertEqual(
            sequence,
            ["major", "minor", "combination", "major"] * 2,
        )
        self.assertTrue(exact_ratio(counts))

        tied = choose_category(
            {"major": 1, "minor": 0, "combination": 0},
            combination_eligible=True,
        )
        self.assertEqual(tied, "minor")

    def test_combination_is_skipped_until_provenance_is_eligible(self):
        counts = {"major": 1, "minor": 1, "combination": 0}
        self.assertEqual(choose_category(counts, combination_eligible=False), "major")
        self.assertEqual(
            choose_category(counts, combination_eligible=True), "combination"
        )
        decision = schedule_decision(
            {"major": 2, "minor": 1, "combination": 0},
            control_state="consumed",
            current_attempt=None,
            combination_eligible=False,
            final_targets={
                "completed_candidates": 4,
                "major_candidates": 2,
                "minor_candidates": 1,
                "combination_candidates": 1,
            },
        )
        self.assertEqual(decision["action"], "blocked")
        self.assertIn("no validated compatible source set", decision["reason"])

    def test_every_scheduler_phase_reaches_smallest_exact_final_ratio(self):
        counts = {"major": 0, "minor": 0, "combination": 0}
        phases = [copy.deepcopy(counts)]
        for _ in range(12):
            category = choose_category(counts, combination_eligible=True)
            counts[category] += 1
            phases.append(copy.deepcopy(counts))

        for stop_counts in phases:
            with self.subTest(stop_counts=stop_counts):
                final = minimal_final_targets(stop_counts)
                simulated = copy.deepcopy(stop_counts)
                while any(finalization_deficits(simulated, final).values()):
                    decision = schedule_decision(
                        simulated,
                        control_state="consumed",
                        current_attempt=None,
                        combination_eligible=True,
                        final_targets=final,
                    )
                    self.assertEqual(decision["action"], "schedule-finalization")
                    simulated[decision["category"]] += 1
                self.assertTrue(exact_ratio(simulated))
                self.assertEqual(sum(simulated.values()) % 4, 0)

    def test_active_candidate_finishes_before_stop_consumption(self):
        current = {
            "candidate": "Genesis",
            "mechanism_key": "fresh-genesis-baseline",
            "mechanism_family": "fresh Genesis baseline",
            "classification": "baseline",
            "controlled_stage": "running Development evaluator",
            "state": "running",
            "started_at": "2026-09-01T09:30:00Z",
            "scheduling": "ordinary",
        }
        raw = self.raw_state(current=current)
        observed, changed = observe_stop_request(raw, [self.durable_issue()], NOW)
        self.assertTrue(changed)
        decision = schedule_decision(
            {"major": 0, "minor": 0, "combination": 0},
            control_state=observed["control"]["state"],
            current_attempt=observed["current_attempt"],
            combination_eligible=False,
            final_targets=None,
        )
        self.assertEqual(decision["action"], "finish-active")
        with self.assertRaisesRegex(ControlError, "active candidate"):
            consume_stop_request(
                observed, {"major": 0, "minor": 0, "combination": 0}, NOW
            )

        observed["current_attempt"] = None
        consumed, changed = consume_stop_request(
            observed, {"major": 1, "minor": 0, "combination": 0}, NOW
        )
        self.assertTrue(changed)
        self.assertEqual(
            consumed["scheduler"]["final_targets"],
            {
                "completed_candidates": 4,
                "major_candidates": 2,
                "minor_candidates": 1,
                "combination_candidates": 1,
            },
        )

    def test_request_is_durable_idempotent_and_rejects_stale_replay(self):
        forge = FakeForge(self.snapshot(), [self.pull()])
        first = request_stop(
            forge,
            campaign_id="continuous-test-20260901",
            branch="autoresearch-acts-seeding/continuous-test",
            control_id="c" * 64,
            context=self.context(),
            requested_at=NOW,
        )
        self.assertEqual(first["issue_number"], 71)
        self.assertTrue(forge.label_ensured)
        forge.issues = forge.created[:]
        second = request_stop(
            forge,
            campaign_id="continuous-test-20260901",
            branch="autoresearch-acts-seeding/continuous-test",
            control_id="c" * 64,
            context=self.context(901),
            requested_at=NOW,
        )
        self.assertEqual(second, first)
        self.assertEqual(len(forge.created), 1)

        forge.issues = [self.durable_issue(control_id="d" * 64)]
        with self.assertRaisesRegex(ControlError, "stale or replayed"):
            request_stop(
                forge,
                campaign_id="continuous-test-20260901",
                branch="autoresearch-acts-seeding/continuous-test",
                control_id="c" * 64,
                context=self.context(),
                requested_at=NOW,
            )

    def test_restart_recovery_keeps_observed_and_consumed_request(self):
        observed, _ = observe_stop_request(
            self.raw_state(), [self.durable_issue()], NOW
        )
        recovered = validate_live_state(json.loads(json.dumps(observed)))
        repeated, changed = observe_stop_request(recovered, [self.durable_issue()], NOW)
        self.assertFalse(changed)
        consumed, changed = consume_stop_request(
            repeated, {"major": 2, "minor": 1, "combination": 0}, NOW
        )
        self.assertTrue(changed)
        recovered_consumed = validate_live_state(json.loads(json.dumps(consumed)))
        same, changed = consume_stop_request(
            recovered_consumed, {"major": 2, "minor": 1, "combination": 0}, NOW
        )
        self.assertFalse(changed)
        self.assertEqual(
            same["scheduler"]["final_targets"], consumed["scheduler"]["final_targets"]
        )

    def test_malformed_unknown_completed_and_non_continuous_requests_refuse(self):
        with self.assertRaises(ControlError):
            observe_stop_request(
                self.raw_state(),
                [{**self.durable_issue(), "body": "edited"}],
                NOW,
            )
        forge = FakeForge(None, [self.pull()])
        with self.assertRaisesRegex((ControlError, RuntimeError), "not found"):
            request_stop(
                forge,
                campaign_id="continuous-test-20260901",
                branch="autoresearch-acts-seeding/continuous-test",
                control_id="c" * 64,
                context=self.context(),
                requested_at=NOW,
            )

        completed_raw = self.raw_state(
            control={
                "state": "completed",
                "request": {
                    "campaign_id": "continuous-test-20260901",
                    "campaign_branch": "autoresearch-acts-seeding/continuous-test",
                    "control_id": "c" * 64,
                    "issue_number": 71,
                    "issue_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/issues/71",
                    "requested_at": "2026-09-01T10:00:00Z",
                    "requested_by": "captain",
                    "workflow_run_id": 900,
                    "workflow_run_attempt": 1,
                    "workflow_run_url": "https://github.com/Aksth070600/autoresearch-acts-seeding/actions/runs/900",
                },
                "observed_at": "2026-09-01T10:01:00Z",
                "consumed_at": "2026-09-01T10:02:00Z",
                "completed_at": "2026-09-01T10:03:00Z",
            },
            scheduler={
                "state": "completed",
                "combination_readiness": None,
                "final_targets": {
                    "completed_candidates": 4,
                    "major_candidates": 2,
                    "minor_candidates": 1,
                    "combination_candidates": 1,
                },
                "blocker": None,
            },
        )
        # Completion evidence is checked elsewhere. Isolate the terminal
        # dispatch refusal here so no scientific fixture is needed.
        completed_snapshot = self.snapshot()
        completed_snapshot["control"] = completed_raw["control"]
        completed_snapshot["scheduler"]["state"] = "completed"
        completed_snapshot["scheduler"]["final_targets"] = completed_raw["scheduler"][
            "final_targets"
        ]
        completed_snapshot["scheduler"]["decision"] = {
            "action": "complete",
            "category": None,
            "reason": "The completed campaign is immutable.",
        }
        forge = FakeForge(completed_snapshot, [self.pull()])
        with (
            patch("campaign_control.validate_status"),
            self.assertRaisesRegex(ControlError, "completed campaigns"),
        ):
            request_stop(
                forge,
                campaign_id="continuous-test-20260901",
                branch="autoresearch-acts-seeding/continuous-test",
                control_id="c" * 64,
                context=self.context(),
                requested_at=NOW,
            )

        fixed = copy.deepcopy(self.snapshot())
        fixed["campaign"].pop("mode")
        fixed["campaign"].pop("campaign_id")
        fixed["campaign"].pop("control_id")
        fixed["campaign"].pop("genesis_commit")
        fixed["campaign"]["targets"] = {
            "completed_candidates": 20,
            "major_candidates": 10,
            "minor_candidates": 5,
            "combination_candidates": 5,
        }
        fixed["schema_version"] = "1.0.0"
        fixed.pop("control")
        fixed.pop("scheduler")
        fixed["progress"].pop("composition")
        validate_status(fixed)
        forge = FakeForge(fixed, [self.pull()])
        with self.assertRaisesRegex(ControlError, "not continuous"):
            request_stop(
                forge,
                campaign_id="continuous-test-20260901",
                branch="autoresearch-acts-seeding/continuous-test",
                control_id="c" * 64,
                context=self.context(),
                requested_at=NOW,
            )

    def test_finalization_reports_exact_ratio_and_genesis_blockers(self):
        observed, _ = observe_stop_request(
            self.raw_state(), [self.durable_issue()], NOW
        )
        consumed, _ = consume_stop_request(
            observed, {"major": 0, "minor": 0, "combination": 0}, NOW
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", repository], check=True)
            subprocess.run(
                ["git", "-C", repository, "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", repository, "config", "user.name", "Test"], check=True
            )
            optimization = repository / "optimization-files"
            optimization.mkdir()
            (optimization / "genesis.cpp").write_text("genesis\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repository, "commit", "-qm", "Genesis"], check=True
            )
            genesis = subprocess.check_output(
                ["git", "-C", repository, "rev-parse", "HEAD"], text=True
            ).strip()
            consumed["campaign"]["genesis_commit"] = genesis
            records = repository / "records"
            records.mkdir()
            blockers = finalization_blockers(consumed, [], records, repository)
        self.assertTrue(any("final category deficits" in item for item in blockers))
        self.assertTrue(any("Development Genesis" in item for item in blockers))

    def test_graceful_finalization_passes_with_ratio_evidence_and_genesis(self):
        observed, _ = observe_stop_request(
            self.raw_state(), [self.durable_issue()], NOW
        )
        consumed, _ = consume_stop_request(
            observed, {"major": 0, "minor": 0, "combination": 0}, NOW
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", repository], check=True)
            subprocess.run(
                ["git", "-C", repository, "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", repository, "config", "user.name", "Test"], check=True
            )
            optimization = repository / "optimization-files"
            optimization.mkdir()
            (optimization / "genesis.cpp").write_text("genesis\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repository, "commit", "-qm", "Genesis"], check=True
            )
            genesis_commit = subprocess.check_output(
                ["git", "-C", repository, "rev-parse", "HEAD"], text=True
            ).strip()
            commits = []
            for name in ("MajorA", "MinorA", "MajorB", "Combined"):
                subprocess.run(
                    ["git", "-C", repository, "commit", "--allow-empty", "-qm", name],
                    check=True,
                )
                commits.append(
                    subprocess.check_output(
                        ["git", "-C", repository, "rev-parse", "HEAD"], text=True
                    ).strip()
                )

            def proposal(candidate, commit, provenance=None):
                return {
                    "schema_version": "1.0.0",
                    "candidate": candidate,
                    "implementation_commit": commit,
                    "hypothesis": "The focused mechanism should reduce seeding time.",
                    "falsifier": "Seeding time does not decrease.",
                    "predicted_directions": {
                        "timed_seeding_time_per_event_ms": "decrease",
                        "timed_seeding_particle_efficiency": "unchanged",
                    },
                    "expected_hot_path": "The accepted-item seeding traversal.",
                    "changed_symbols": [f"{candidate}::run"],
                    "intended_files": ["optimization-files/genesis.cpp"],
                    "novelty_reason": f"{candidate} tests a distinct mechanism.",
                    "source_references": [
                        {
                            "source_type": "Genesis",
                            "reference": "records/Development/Genesis/summary.json",
                            "relevance": "The baseline identifies the hot path.",
                            "directly_inspected": True,
                        }
                    ],
                    "combination_provenance": provenance,
                }

            candidates = ["MajorA", "MinorA", "MajorB"]
            classifications = ["major", "minor", "major"]
            metadata = []
            for candidate, classification, commit in zip(
                candidates, classifications, commits
            ):
                metadata.append(
                    {
                        "candidate": candidate,
                        "mechanism_key": f"{candidate.lower()}-mechanism",
                        "mechanism_family": f"{candidate.lower()}-family",
                        "classification": classification,
                        "proposal": proposal(candidate, commit),
                        "evidence": {
                            "files_changed": ["optimization-files/genesis.cpp#L1-L1"],
                            "outcome": "keep",
                            "lesson": "The measured mechanism has complete evidence.",
                            "prediction_assessment": "held",
                            "prediction_assessment_rationale": "The primary objectives followed the prediction.",
                        },
                    }
                )
            provenance = {
                "sources": [
                    {
                        "candidate": "MajorA",
                        "mechanism_key": "majora-mechanism",
                        "implementation_commit": commits[0],
                        "directly_inspected": True,
                    },
                    {
                        "candidate": "MinorA",
                        "mechanism_key": "minora-mechanism",
                        "implementation_commit": commits[1],
                        "directly_inspected": True,
                    },
                ],
                "compatibility_rationale": "The mechanisms affect separate seams.",
                "interaction_hypothesis": "Their effects should combine additively.",
            }
            metadata.append(
                {
                    "candidate": "Combined",
                    "mechanism_key": "combined-mechanism",
                    "mechanism_family": "combined-family",
                    "classification": "combination",
                    "proposal": proposal("Combined", commits[3], provenance),
                    "combination_provenance": provenance,
                    "evidence": {
                        "files_changed": ["optimization-files/genesis.cpp#L1-L1"],
                        "outcome": "keep",
                        "lesson": "The measured combination has complete evidence.",
                        "prediction_assessment": "held",
                        "prediction_assessment_rationale": "The primary objectives followed the prediction.",
                    },
                }
            )
            consumed["campaign"]["genesis_commit"] = genesis_commit
            consumed["attempt_metadata"] = metadata
            state = validate_live_state(consumed)
            attempts = [
                {
                    "candidate": "Genesis",
                    "state": "completed",
                    "classification": "baseline",
                    "implementation_commit": genesis_commit,
                },
                *[
                    {
                        "candidate": candidate,
                        "state": "completed",
                        "classification": classification,
                        "implementation_commit": commit,
                    }
                    for candidate, classification, commit in zip(
                        ["MajorA", "MinorA", "MajorB", "Combined"],
                        ["major", "minor", "major", "combination"],
                        commits,
                    )
                ],
            ]
            records = repository / "records"
            records.mkdir()
            blockers = finalization_blockers(state, attempts, records, repository)
        self.assertEqual(blockers, [])

    def test_continuous_evaluator_rejects_evaluation_post_stop_and_repeat(self):
        raw = self.raw_state(
            current={
                "candidate": "Genesis",
                "mechanism_key": "fresh-genesis-baseline",
                "mechanism_family": "fresh Genesis baseline",
                "classification": "baseline",
                "controlled_stage": "queued Development run",
                "state": "queued",
                "started_at": "2026-09-01T09:10:00Z",
                "scheduling": "ordinary",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "campaign.json"
            records = root / "records"
            records.mkdir()
            input_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationError, "Development-only"):
                enforce_continuous_development_run(input_path, "Genesis", True, records)
            completed = records / "Development" / "Genesis"
            completed.mkdir(parents=True)
            (completed / "summary.json").write_text(
                json.dumps(
                    {
                        "candidate_name": "Genesis",
                        "status": "passed",
                        "mode": "development",
                        "started_at": "2026-09-01T09:20:00Z",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(EvaluationError, "repeat a completed"):
                enforce_continuous_development_run(
                    input_path, "Genesis", False, records
                )
            shutil.rmtree(completed)
            observed, _ = observe_stop_request(raw, [self.durable_issue()], NOW)
            input_path.write_text(json.dumps(observed), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationError, "cannot start"):
                enforce_continuous_development_run(
                    input_path, "Genesis", False, records
                )

    @staticmethod
    def dashboard_logic():
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "campaign" / "index.html"
            render(output)
            html = output.read_text(encoding="utf-8")
        return html.split("/* CAMPAIGN_DISCOVERY_LOGIC_START */", 1)[1].split(
            "/* CAMPAIGN_DISCOVERY_LOGIC_END */", 1
        )[0], html

    def test_dashboard_finish_control_visibility_and_unavailable_states(self):
        if shutil.which("node") is None:
            self.skipTest("node is required")
        logic, _ = self.dashboard_logic()
        snapshot = self.snapshot()
        campaign = {
            "state": "open",
            "ref": "autoresearch-acts-seeding/continuous-test",
        }
        script = (
            logic
            + f"\nconst snapshot = {json.dumps(snapshot)};"
            + f"\nconst campaign = {json.dumps(campaign)};"
            + "\nconst available = finishControlModel(snapshot, campaign);"
            + "\nconst requested = finishControlModel({...snapshot, control: {...snapshot.control, state: 'requested'}}, campaign);"
            + "\nconst closed = finishControlModel(snapshot, {...campaign, state: 'closed'});"
            + "\nconst fixed = finishControlModel({...snapshot, campaign: {...snapshot.campaign, mode: 'fixed'}}, campaign);"
            + "\nconsole.log(JSON.stringify({available, requested, closed, fixed}));"
        )
        result = subprocess.run(
            ["node", "-e", script], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        models = json.loads(result.stdout)
        self.assertTrue(models["available"]["available"])
        self.assertIn(
            "actions/workflows/finish-campaign.yml", models["available"]["workflowUrl"]
        )
        self.assertFalse(models["requested"]["available"])
        self.assertIn("active candidate", models["requested"]["status"])
        self.assertIn("immutable", models["closed"]["status"])
        self.assertIn("fixed archive", models["fixed"]["status"])

    def test_page_has_no_credential_or_privileged_request(self):
        _, html = self.dashboard_logic()
        self.assertIn("Finish campaign", html)
        self.assertNotIn("GITHUB_TOKEN", html)
        self.assertNotIn("Authorization:", html)
        self.assertNotIn("method: 'POST'", html)
        self.assertNotIn("api.github.com/repos/${REPOSITORY}/actions", html)
        self.assertIn("credentials: 'omit'", html)

    def test_workflow_permissions_validation_and_shell_safety(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "finish-campaign.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertIn("issues: write", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("CAMPAIGN_BRANCH: ${{ inputs.campaign_branch }}", workflow)
        self.assertIn('--branch "$CAMPAIGN_BRANCH"', workflow)
        self.assertNotIn("--branch ${{", workflow)


if __name__ == "__main__":
    unittest.main()
