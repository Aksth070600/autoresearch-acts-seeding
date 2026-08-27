import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from campaign_status import (  # noqa: E402
    STATUS_SCHEMA_VERSION,
    StatusError,
    atomic_write_json,
    build_status,
    calculate_eta,
    load_attempts,
    validate_live_state,
    validate_status,
)
from protocol import current_protocol  # noqa: E402
from visualizations.campaign import freshness_state, render, validate_ref  # noqa: E402


UTC = timezone.utc


class CampaignStatusTests(unittest.TestCase):
    def live_state(self, metadata=None, current=None, blockers=None) -> dict:
        return validate_live_state(
            {
                "schema_version": STATUS_SCHEMA_VERSION,
                "campaign": {
                    "name": "Campaign test",
                    "branch": "autoresearch-acts-seeding/test-v1",
                    "phase": "exploration",
                    "started_at": "2026-08-27T09:00:00Z",
                },
                "current_attempt": current,
                "attempt_metadata": metadata or [],
                "blockers": blockers or [],
                "pull_request_url": (
                    "https://github.com/Aksth070600/autoresearch-acts-seeding/pull/42"
                ),
            }
        )

    @staticmethod
    def summary(
        candidate: str,
        started_at: str,
        duration_seconds: int,
        seeding_ms: float,
        efficiency: float,
        *,
        passed: bool = True,
        commit: str = "a" * 40,
    ) -> dict:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        run_metrics = {
            "timing_total": {"time_per_event_ms": seeding_ms + 5000},
            "timing": {"seeding": {"time_per_event_ms": seeding_ms}},
            "performance": {
                "ambiguity_resolution": {"efficiency_particles": efficiency}
            },
        }
        return {
            "candidate_name": candidate,
            "protocol_id": "acts-seeding-v2",
            "protocol": current_protocol(),
            "implementation_commit": commit,
            "mode": "development",
            "category": "Development" if passed else "Failed",
            "status": "passed" if passed else "failed",
            "started_at": started_at,
            "finished_at": (
                started + timedelta(seconds=duration_seconds)
            ).isoformat(),
            "stages": [
                {
                    "name": "controlled-development",
                    "status": "passed" if passed else "failed",
                }
            ],
            "timed_comparison": {
                "aggregation": "median",
                "repetition_count": 3,
                "required_repetitions": 3,
                "complete": passed,
                "repetitions": [
                    {
                        "repetition": number,
                        "status": "passed",
                        "run_metrics": run_metrics,
                    }
                    for number in (1, 2, 3)
                ],
                "median_run_metrics": run_metrics,
            },
            **({} if passed else {"error": "Candidate failed the controlled stage."}),
        }

    def write_summary(self, records: Path, name: str, summary: dict) -> None:
        category = summary["category"]
        folder = records / category / name
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )

    def test_schema_validation_and_atomic_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            records.mkdir()
            state = self.live_state()
            status = build_status(
                state,
                load_attempts(records, state),
                datetime(2026, 8, 27, 10, tzinfo=UTC),
                "b" * 40,
            )
            validate_status(status)
            output = Path(temporary) / "campaign-status.json"
            atomic_write_json(output, status)

            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], "1.0.0")
            self.assertFalse(list(output.parent.glob(".campaign-status.json.*.tmp")))
            invalid = copy.deepcopy(status)
            invalid["schema_version"] = "2.0.0"
            with self.assertRaisesRegex(StatusError, "schema version"):
                validate_status(invalid)

        schema = json.loads(
            (PROJECT_ROOT / "orchestration-files" / "campaign-status.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0.0")
        self.assertEqual(schema["properties"]["protocol_id"]["const"], "acts-seeding-v2")
        self.assertFalse(schema["additionalProperties"])

    def test_derives_latest_genesis_promising_results_and_pareto_front(self) -> None:
        metadata = [
            {
                "candidate": candidate,
                "mechanism_family": mechanism,
                "classification": classification,
            }
            for candidate, mechanism, classification in (
                ("Fast", "bounds", "structural"),
                ("Efficient", "filter", "structural"),
                ("Dominated", "hint", "micro"),
                ("Broken", "layout", "structural"),
            )
        ]
        state = self.live_state(metadata)
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            records.mkdir()
            rows = (
                ("g1", self.summary("Genesis", "2026-08-27T09:05:00Z", 90, 100, 0.90)),
                ("g2", self.summary("Genesis", "2026-08-27T09:10:00Z", 100, 90, 0.91)),
                ("fast", self.summary("Fast", "2026-08-27T09:20:00Z", 120, 80, 0.88)),
                ("efficient", self.summary("Efficient", "2026-08-27T09:30:00Z", 180, 110, 0.95)),
                ("dominated", self.summary("Dominated", "2026-08-27T09:40:00Z", 300, 120, 0.80)),
                (
                    "broken",
                    self.summary(
                        "Broken", "2026-08-27T09:50:00Z", 40, 1, 1, passed=False
                    ),
                ),
            )
            for name, summary in rows:
                self.write_summary(records, name, summary)

            attempts = load_attempts(records, state)
            now = datetime(2026, 8, 27, 12, tzinfo=UTC)
            status = build_status(state, attempts, now, "c" * 40)
            repeated = build_status(state, attempts, now, "c" * 40)

        self.assertEqual(status, repeated)
        promising = status["promising_results"]
        self.assertEqual(promising["latest_genesis"]["started_at"], "2026-08-27T09:10:00Z")
        self.assertEqual(promising["best_seeding"]["candidate"], "Fast")
        self.assertEqual(promising["best_seeding"]["delta_vs_genesis_ms"], -10)
        self.assertAlmostEqual(
            promising["best_seeding"]["percentage_vs_genesis"], -100 / 9
        )
        self.assertEqual(promising["best_ambiguity_efficiency"]["candidate"], "Efficient")
        self.assertEqual(
            {point["candidate"] for point in promising["pareto_front"]},
            {"Genesis", "Fast", "Efficient"},
        )
        self.assertEqual(status["progress"]["completed_attempts"], 3)
        self.assertEqual(status["progress"]["structural_attempts"], 3)
        self.assertEqual(status["progress"]["micro_optimizations"], 1)
        self.assertEqual(status["progress"]["median_completed_attempt_duration_seconds"], 180)
        self.assertEqual([failure["candidate"] for failure in status["failures"]], ["Broken"])
        serialized = json.dumps(status)
        self.assertNotIn("timed_total", serialized)
        self.assertNotIn("full_chain", serialized)

    def test_eta_requires_samples_uses_median_and_deducts_current_elapsed(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=UTC)
        unavailable = calculate_eta([100, 200], 4, now)
        self.assertIsNone(unavailable["remaining_seconds"])
        self.assertIn("3 completed", unavailable["basis"])

        estimate = calculate_eta(
            [100, 200, 300],
            4,
            now,
            current_started_at=now - timedelta(seconds=50),
            current_is_pending=True,
        )
        self.assertEqual(estimate["median_seconds"], 200)
        self.assertEqual(estimate["remaining_seconds"], 750)
        self.assertEqual(
            estimate["expected_finish_at"], "2026-08-27T12:12:30Z"
        )
        self.assertIn("elapsed time deducted", estimate["basis"])

        blocked = calculate_eta([100, 200, 300], 4, now, blocked=True)
        self.assertIsNone(blocked["remaining_seconds"])
        self.assertIn("blocked", blocked["basis"])

    def test_input_accepts_only_non_scientific_state_and_safe_refs(self) -> None:
        raw = {
            "schema_version": "1.0.0",
            "campaign": {
                "name": "Campaign test",
                "branch": "safe/team-campaign.v1",
                "phase": "exploration",
                "started_at": "2026-08-27T09:00:00Z",
            },
            "current_attempt": None,
            "attempt_metadata": [],
            "blockers": [],
            "pull_request_url": None,
        }
        self.assertEqual(validate_live_state(raw)["campaign"]["branch"], "safe/team-campaign.v1")
        self.assertEqual(validate_ref("safe/team-campaign.v1"), "safe/team-campaign.v1")

        for unsafe in ("../main", "team//campaign", "team/@{main", "-branch", ".hidden/x", "branch lock"):
            with self.subTest(unsafe=unsafe), self.assertRaises(StatusError):
                validate_ref(unsafe)

        scientific = copy.deepcopy(raw)
        scientific["timed_seeding_time_per_event_ms"] = 1.0
        with self.assertRaisesRegex(StatusError, "unsupported fields"):
            validate_live_state(scientific)

    def test_unknown_campaign_candidate_requires_classification_metadata(self) -> None:
        state = self.live_state()
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            records.mkdir()
            self.write_summary(
                records,
                "unknown",
                self.summary("Unknown", "2026-08-27T10:00:00Z", 100, 50, 0.9),
            )
            with self.assertRaisesRegex(StatusError, "add non-scientific metadata"):
                load_attempts(records, state)

    def test_dashboard_html_has_empty_stale_error_and_interactive_essentials(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=UTC)
        self.assertEqual(freshness_state("2026-08-27T11:59:00Z", now), "fresh")
        self.assertEqual(freshness_state("2026-08-27T11:50:00Z", now), "aging")
        self.assertEqual(freshness_state("2026-08-27T11:40:00Z", now), "stale")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "campaign" / "index.html"
            render(output)
            html = output.read_text(encoding="utf-8")

        for essential in (
            "ACTS Seeding Live Campaign",
            'id="empty-state"',
            'id="fetch-error"',
            "Showing the last good snapshot",
            "Current two-objective Pareto front",
            "Attempt history",
            "Timed seeding time/event (ms) · lower is better",
            "Particle ambiguity efficiency · higher is better",
            "const POLL_INTERVAL_MS = 60000;",
            "cache: 'no-store'",
            "credentials: 'omit'",
            "refs/heads/${encodedRef}",
            "function safeRef(raw)",
            "function freshnessState(snapshot)",
        ):
            self.assertIn(essential, html)
        self.assertNotIn("full-chain time", html.lower())
        self.assertNotIn("timed_total_time_per_event_ms", html)


if __name__ == "__main__":
    unittest.main()
