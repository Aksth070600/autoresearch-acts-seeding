import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from campaign_status import (  # noqa: E402
    DEFAULT_INPUT,
    DEFAULT_OUTPUT,
    SNAPSHOT_PATH,
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
    def live_state(
        self, metadata=None, current=None, blockers=None, targets=None, *, legacy=False
    ) -> dict:
        campaign = {
            "name": "Campaign test",
            "branch": "autoresearch-acts-seeding/test-v1",
            "phase": "exploration",
            "started_at": "2026-08-27T09:00:00Z",
        }
        if targets is not None:
            campaign["targets"] = targets
        elif legacy:
            campaign["targets"] = {
                "completed_attempts": 20,
                "structural_attempts": 10,
                "micro_optimization_cap": 5,
            }
        return validate_live_state(
            {
                "schema_version": STATUS_SCHEMA_VERSION,
                "campaign": campaign,
                "current_attempt": current,
                "attempt_metadata": metadata or [],
                "blockers": blockers or [],
                "pull_request_url": (
                    "https://github.com/Aksth070600/autoresearch-acts-seeding/pull/42"
                ),
            }
        )

    @staticmethod
    def candidate_metadata(
        candidate: str,
        classification: str = "major",
        *,
        commit: str = "a" * 40,
        mechanism_key: str | None = None,
        mechanism_family: str | None = None,
        evidence: bool = True,
        combination_provenance: dict | None = None,
    ) -> dict:
        key = mechanism_key or f"{candidate.lower()}-mechanism"
        item = {
            "candidate": candidate,
            "mechanism_key": key,
            "mechanism_family": mechanism_family or key,
            "classification": classification,
        }
        if evidence:
            item["evidence"] = {
                "implementation_commit": commit,
                "changed_symbols": [f"{candidate}::run"],
                "files_changed": [
                    f"optimization-files/Core/src/{candidate}.cpp#L10-L20"
                ],
                "hot_path_rationale": "Reduce work in the accepted hot path.",
                "novelty_rationale": "This mechanism is distinct from earlier candidates.",
                "outcome": "keep",
                "lesson": "The focused mechanism completed controlled Development.",
            }
        if combination_provenance is not None:
            item["combination_provenance"] = combination_provenance
        return item

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
            self.assertEqual(written["repository"]["snapshot_path"], SNAPSHOT_PATH)
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
        self.assertEqual(
            schema["properties"]["repository"]["properties"]["snapshot_path"]["enum"],
            [
                "orchestration-files/campaign-status.json",
                "campaign-status.json",
            ],
        )
        self.assertEqual(
            DEFAULT_INPUT.relative_to(PROJECT_ROOT).as_posix(),
            "orchestration-files/campaign-status-input.json",
        )
        self.assertEqual(
            DEFAULT_OUTPUT.relative_to(PROJECT_ROOT).as_posix(),
            "orchestration-files/campaign-status.json",
        )
        self.assertFalse(schema["additionalProperties"])
        target_variants = schema["$defs"]["campaignTargets"]["oneOf"]
        required_sets = {frozenset(variant["required"]) for variant in target_variants}
        self.assertIn(
            frozenset(
                {
                    "completed_candidates",
                    "major_candidates",
                    "minor_candidates",
                    "combination_candidates",
                }
            ),
            required_sets,
        )
        historical = json.loads(
            (PROJECT_ROOT / "orchestration-files" / "campaign-status.json").read_text(
                encoding="utf-8"
            )
        )
        validate_status(historical)

    def test_candidate_commit_link_skips_following_status_only_commit(self) -> None:
        state = self.live_state(
            [
                {
                    "candidate": "Candidate",
                    "mechanism_family": "candidate-mechanism",
                    "classification": "structural",
                }
            ],
            legacy=True,
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            subprocess.run(["git", "init", "-q", repository], check=True)
            subprocess.run(
                ["git", "-C", repository, "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", repository, "config", "user.name", "Campaign Test"],
                check=True,
            )
            implementation = repository / "optimization-files" / "candidate.cpp"
            implementation.parent.mkdir()
            implementation.write_text("candidate\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repository, "commit", "-q", "-m", "Implement candidate"],
                check=True,
            )
            implementation_commit = subprocess.check_output(
                ["git", "-C", repository, "rev-parse", "HEAD"], text=True
            ).strip()

            status_path = repository / "orchestration-files" / "campaign-status.json"
            status_path.parent.mkdir()
            status_path.write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "-C", repository, "add", "."], check=True)
            subprocess.run(
                ["git", "-C", repository, "commit", "-q", "-m", "Queue candidate"],
                check=True,
            )
            status_commit = subprocess.check_output(
                ["git", "-C", repository, "rev-parse", "HEAD"], text=True
            ).strip()

            records = repository / "records"
            records.mkdir()
            self.write_summary(
                records,
                "genesis",
                self.summary(
                    "Genesis",
                    "2026-08-27T09:05:00Z",
                    90,
                    100,
                    0.90,
                    commit=status_commit,
                ),
            )
            self.write_summary(
                records,
                "candidate",
                self.summary(
                    "Candidate",
                    "2026-08-27T09:10:00Z",
                    90,
                    90,
                    0.90,
                    commit=status_commit,
                ),
            )

            attempts = load_attempts(records, state, repository)

        by_candidate = {attempt["candidate"]: attempt for attempt in attempts}
        self.assertEqual(
            by_candidate["Candidate"]["implementation_commit"],
            implementation_commit,
        )
        self.assertEqual(
            by_candidate["Candidate"]["links"]["commit"],
            f"https://github.com/Aksth070600/autoresearch-acts-seeding/commit/{implementation_commit}",
        )
        self.assertEqual(
            by_candidate["Genesis"]["links"]["commit"],
            "https://github.com/Aksth070600/autoresearch-acts-seeding",
        )

    def test_derives_latest_genesis_promising_results_and_pareto_front(self) -> None:
        metadata = [
            self.candidate_metadata(
                candidate,
                classification,
                mechanism_key=mechanism,
                mechanism_family=mechanism,
            )
            for candidate, mechanism, classification in (
                ("Fast", "bounds", "major"),
                ("Efficient", "filter", "major"),
                ("Dominated", "hint", "minor"),
                ("Broken", "layout", "major"),
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
        self.assertEqual(status["progress"]["completed_candidates"], 3)
        self.assertEqual(status["progress"]["major_candidates"], 2)
        self.assertEqual(status["progress"]["minor_candidates"], 1)
        self.assertEqual(status["progress"]["combination_candidates"], 0)
        self.assertEqual(status["progress"]["median_completed_attempt_duration_seconds"], 180)
        self.assertEqual([failure["candidate"] for failure in status["failures"]], ["Broken"])
        serialized = json.dumps(status)
        self.assertNotIn("timed_total", serialized)
        self.assertNotIn("full_chain", serialized)

    def test_explicit_campaign_targets_override_defaults_and_drive_progress(self) -> None:
        special_targets = {
            "completed_candidates": 1,
            "major_candidates": 1,
            "minor_candidates": 0,
            "combination_candidates": 0,
        }
        state = self.live_state(
            metadata=[self.candidate_metadata("MajorCandidate")],
            targets=special_targets,
        )
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            records.mkdir()
            self.write_summary(
                records,
                "composite",
                self.summary(
                    "MajorCandidate",
                    "2026-08-27T10:00:00Z",
                    100,
                    90,
                    0.9,
                ),
            )
            status = build_status(
                state,
                load_attempts(records, state),
                datetime(2026, 8, 27, 11, tzinfo=UTC),
                "d" * 40,
            )

        self.assertEqual(status["campaign"]["targets"], special_targets)
        self.assertEqual(status["progress"]["completed_candidates"], 1)
        self.assertEqual(status["progress"]["major_candidates"], 1)
        self.assertEqual(status["progress"]["estimated_remaining_seconds"], 0)
        self.assertEqual(
            self.live_state()["campaign"]["targets"],
            {
                "completed_candidates": 20,
                "major_candidates": 10,
                "minor_candidates": 5,
                "combination_candidates": 5,
            },
        )

        for invalid in (
            {**special_targets, "completed_candidates": 0},
            {**special_targets, "major_candidates": 2},
            {**special_targets, "minor_candidates": 1},
            {**special_targets, "combination_candidates": True},
        ):
            with self.subTest(targets=invalid), self.assertRaises(StatusError):
                self.live_state(targets=invalid)

    def test_status_rejects_completed_category_overrun_and_missing_evidence(self) -> None:
        targets = {
            "completed_candidates": 1,
            "major_candidates": 1,
            "minor_candidates": 0,
            "combination_candidates": 0,
        }
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            records.mkdir()
            self.write_summary(
                records,
                "first",
                self.summary("First", "2026-08-27T10:00:00Z", 100, 90, 0.9),
            )
            missing_evidence = self.live_state(
                [self.candidate_metadata("First", evidence=False)], targets=targets
            )
            with self.assertRaisesRegex(StatusError, "no completed evidence"):
                load_attempts(records, missing_evidence)

            self.write_summary(
                records,
                "second",
                self.summary("Second", "2026-08-27T10:05:00Z", 100, 89, 0.9),
            )
            overrun = self.live_state(
                [self.candidate_metadata("First"), self.candidate_metadata("Second")],
                targets=targets,
            )
            with self.assertRaisesRegex(StatusError, "exceed the campaign target"):
                build_status(
                    overrun,
                    load_attempts(records, overrun),
                    datetime(2026, 8, 27, 11, tzinfo=UTC),
                    "d" * 40,
                )

    def test_combination_provenance_names_inspected_earlier_sources(self) -> None:
        source_a = self.candidate_metadata("SourceA", commit="a" * 40)
        source_b = self.candidate_metadata("SourceB", commit="b" * 40)
        provenance = {
            "sources": [
                {
                    "candidate": "SourceA",
                    "mechanism_key": source_a["mechanism_key"],
                    "implementation_commit": "a" * 40,
                    "directly_inspected": True,
                },
                {
                    "candidate": "SourceB",
                    "mechanism_key": source_b["mechanism_key"],
                    "implementation_commit": "b" * 40,
                    "directly_inspected": True,
                },
            ],
            "compatibility_rationale": "The sources change separate seams.",
            "interaction_hypothesis": "Their effects should be additive.",
        }
        combined = self.candidate_metadata(
            "Combined",
            "combination",
            commit="c" * 40,
            combination_provenance=provenance,
        )
        state = self.live_state([source_a, source_b, combined])

        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            records.mkdir()
            for index, (candidate, commit) in enumerate(
                (("SourceA", "a" * 40), ("SourceB", "b" * 40), ("Combined", "c" * 40))
            ):
                self.write_summary(
                    records,
                    candidate,
                    self.summary(
                        candidate,
                        f"2026-08-27T10:0{index}:00Z",
                        100,
                        90 - index,
                        0.9,
                        commit=commit,
                    ),
                )
            status = build_status(
                state,
                load_attempts(records, state),
                datetime(2026, 8, 27, 11, tzinfo=UTC),
                "d" * 40,
            )

        combined_attempt = next(
            attempt for attempt in status["attempts"] if attempt["candidate"] == "Combined"
        )
        self.assertEqual(combined_attempt["combination_provenance"], provenance)
        self.assertEqual(
            combined_attempt["links"]["commit"],
            "https://github.com/Aksth070600/autoresearch-acts-seeding/commit/" + "c" * 40,
        )
        self.assertEqual(status["progress"]["major_candidates"], 2)
        self.assertEqual(status["progress"]["combination_candidates"], 1)

        invalid = copy.deepcopy(provenance)
        invalid["sources"][0]["directly_inspected"] = False
        with self.assertRaisesRegex(StatusError, "directly_inspected"):
            self.live_state(
                [
                    source_a,
                    source_b,
                    self.candidate_metadata(
                        "InvalidCombined",
                        "combination",
                        commit="e" * 40,
                        combination_provenance=invalid,
                    ),
                ]
            )

    def test_rejects_four_consecutive_candidates_from_one_family(self) -> None:
        metadata = [
            self.candidate_metadata(
                f"Candidate{index}",
                "minor",
                mechanism_family="same-family",
            )
            for index in range(4)
        ]
        with self.assertRaisesRegex(StatusError, "three consecutive"):
            self.live_state(metadata)

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
        current = self.live_state(
            current={
                "candidate": "Genesis",
                "mechanism_key": "fresh-genesis-baseline",
                "mechanism_family": "fresh Genesis baseline",
                "classification": "baseline",
                "controlled_stage": "queued Development run",
                "state": "queued",
                "started_at": "2026-08-27T09:05:00Z",
            }
        )["current_attempt"]
        self.assertEqual(current["mechanism_key"], "fresh-genesis-baseline")

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

    @staticmethod
    def dashboard_html() -> str:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "campaign" / "index.html"
            render(output)
            return output.read_text(encoding="utf-8")

    def run_discovery_javascript(self, body: str) -> dict:
        if shutil.which("node") is None:
            self.skipTest("node is required for dashboard JavaScript tests")
        html = self.dashboard_html()
        logic = html.split("/* CAMPAIGN_DISCOVERY_LOGIC_START */", 1)[1].split(
            "/* CAMPAIGN_DISCOVERY_LOGIC_END */", 1
        )[0]
        javascript = (
            logic
            + "\n(async () => {\n"
            + body
            + "\n})().catch((error) => { console.error(error); process.exitCode = 1; });"
        )
        result = subprocess.run(
            ["node", "-e", javascript],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def pull(number: int, branch: str, created_at: str, state: str = "open") -> dict:
        return {
            "number": number,
            "title": f"Campaign {number}",
            "state": state,
            "created_at": created_at,
            "html_url": (
                f"https://github.com/Aksth070600/autoresearch-acts-seeding/pull/{number}"
            ),
            "head": {
                "ref": branch,
                "sha": f"{number:040x}",
                "repo": {"full_name": "Aksth070600/autoresearch-acts-seeding"},
            },
        }

    def test_dashboard_maps_historical_and_new_progress_snapshots(self) -> None:
        historical = {
            "campaign": {
                "targets": {
                    "completed_attempts": 20,
                    "structural_attempts": 10,
                    "micro_optimization_cap": 5,
                }
            },
            "progress": {
                "completed_attempts": 20,
                "structural_attempts": 17,
                "micro_optimizations": 3,
            },
        }
        current = {
            "campaign": {
                "targets": {
                    "completed_candidates": 20,
                    "major_candidates": 10,
                    "minor_candidates": 5,
                    "combination_candidates": 5,
                }
            },
            "progress": {
                "completed_candidates": 8,
                "major_candidates": 5,
                "minor_candidates": 2,
                "combination_candidates": 1,
            },
        }
        result = self.run_discovery_javascript(
            f"const historical = campaignProgressModel({json.dumps(historical)});"
            f"const current = campaignProgressModel({json.dumps(current)});"
            "console.log(JSON.stringify({historical, current}));"
        )

        self.assertEqual(result["historical"]["format"], "legacy-attempts")
        self.assertEqual(
            [card[0] for card in result["historical"]["cards"]],
            ["Completed attempts", "Structural attempts", "Micro-optimizations"],
        )
        self.assertEqual(result["current"]["format"], "candidate-composition")
        self.assertEqual(
            [card[0] for card in result["current"]["cards"]],
            [
                "Completed candidates",
                "Major candidates",
                "Minor candidates",
                "Combination candidates",
            ],
        )

    def test_historical_and_new_snapshot_fixtures_render_progress_cards(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is required for dashboard JavaScript tests")
        html = self.dashboard_html()
        logic = html.split("/* CAMPAIGN_DISCOVERY_LOGIC_START */", 1)[1].split(
            "/* CAMPAIGN_DISCOVERY_LOGIC_END */", 1
        )[0]
        renderer = "function renderCampaignProgress" + html.split(
            "function renderCampaignProgress", 1
        )[1].split("function renderSeedingLeaders", 1)[0]
        historical = {
            "campaign": {
                "targets": {
                    "completed_attempts": 20,
                    "structural_attempts": 10,
                    "micro_optimization_cap": 5,
                }
            },
            "progress": {
                "completed_attempts": 20,
                "structural_attempts": 17,
                "micro_optimizations": 3,
            },
        }
        current = {
            "campaign": {
                "targets": {
                    "completed_candidates": 20,
                    "major_candidates": 10,
                    "minor_candidates": 5,
                    "combination_candidates": 5,
                }
            },
            "progress": {
                "completed_candidates": 8,
                "major_candidates": 5,
                "minor_candidates": 2,
                "combination_candidates": 1,
            },
        }
        javascript = (
            logic
            + "\nconst text = {}; const bars = {}; const combinationCard = {};"
            + "\nfunction setText(id, value) { text[id] = value; }"
            + "\nfunction setProgress(valueId, barId, current, target, cap) { bars[barId] = {current, target, cap}; }"
            + "\nconst document = {getElementById: () => combinationCard};\n"
            + renderer
            + f"\nrenderCampaignProgress({json.dumps(historical)});"
            + "\nconst historicalResult = {text: {...text}, bars: {...bars}, hidden: combinationCard.hidden};"
            + "\nObject.keys(text).forEach((key) => delete text[key]); Object.keys(bars).forEach((key) => delete bars[key]);"
            + f"\nrenderCampaignProgress({json.dumps(current)});"
            + "\nconsole.log(JSON.stringify({historical: historicalResult, current: {text, bars, hidden: combinationCard.hidden}}));"
        )
        result = subprocess.run(
            ["node", "-e", javascript],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        self.assertEqual(rendered["historical"]["text"]["major-label"], "Structural attempts")
        self.assertTrue(rendered["historical"]["hidden"])
        self.assertEqual(rendered["current"]["text"]["major-label"], "Major candidates")
        self.assertEqual(
            rendered["current"]["text"]["combination-label"], "Combination candidates"
        )
        self.assertFalse(rendered["current"]["hidden"])

    def test_campaign_discovery_orders_newest_first_and_defaults_to_newest(self) -> None:
        unsafe_url = self.pull(
            6, "autoresearch-acts-seeding/unsafe-url", "2026-08-29T12:00:00Z"
        )
        unsafe_url["html_url"] = "https://example.com/pull/6"
        pulls = [
            self.pull(3, "autoresearch-acts-seeding/older", "2026-08-25T12:00:00Z"),
            self.pull(5, "autoresearch-acts-seeding/newest", "2026-08-27T12:00:00Z"),
            self.pull(4, "unrelated/branch", "2026-08-28T12:00:00Z"),
            unsafe_url,
        ]
        result = self.run_discovery_javascript(
            f"const campaigns = sortCampaigns({json.dumps(pulls)});"
            "console.log(JSON.stringify({"
            "refs: campaigns.map((campaign) => campaign.ref),"
            "selected: selectInitialCampaign(campaigns, null).ref"
            "}));"
        )
        self.assertEqual(
            result["refs"],
            [
                "autoresearch-acts-seeding/newest",
                "autoresearch-acts-seeding/older",
            ],
        )
        self.assertEqual(result["selected"], "autoresearch-acts-seeding/newest")

    def test_campaign_deep_link_and_discovery_failure_fallback(self) -> None:
        pulls = [
            self.pull(1, "autoresearch-acts-seeding/first", "2026-08-26T12:00:00Z"),
            self.pull(2, "autoresearch-acts-seeding/second", "2026-08-27T12:00:00Z"),
        ]
        result = self.run_discovery_javascript(
            f"const campaigns = sortCampaigns({json.dumps(pulls)});"
            "console.log(JSON.stringify({"
            "deep: selectInitialCampaign(campaigns, 'autoresearch-acts-seeding/first').ref,"
            "fallback: selectInitialCampaign([], 'autoresearch-acts-seeding/manual').ref,"
            "unsafe: selectInitialCampaign([], '../main')"
            "}));"
        )
        self.assertEqual(result["deep"], "autoresearch-acts-seeding/first")
        self.assertEqual(result["fallback"], "autoresearch-acts-seeding/manual")
        self.assertIsNone(result["unsafe"])

    def test_open_campaign_uses_branch_and_completed_campaign_uses_final_sha(self) -> None:
        pulls = [
            self.pull(8, "autoresearch-acts-seeding/running", "2026-08-27T12:00:00Z"),
            self.pull(
                7,
                "autoresearch-acts-seeding/completed",
                "2026-08-26T12:00:00Z",
                state="closed",
            ),
        ]
        result = self.run_discovery_javascript(
            f"const campaigns = sortCampaigns({json.dumps(pulls)});"
            "const open = campaignFetchSource(campaigns.find((item) => item.state === 'open'));"
            "const closed = campaignFetchSource(campaigns.find((item) => item.state === 'closed'));"
            "console.log(JSON.stringify({open, closed, openUrl: snapshotUrl(open, 123), closedUrl: snapshotUrl(closed, 123)}));"
        )
        self.assertEqual(
            result["open"]["fetchRef"],
            "refs/heads/autoresearch-acts-seeding/running",
        )
        self.assertTrue(result["open"]["poll"])
        self.assertFalse(result["open"]["immutable"])
        self.assertEqual(result["closed"]["fetchRef"], f"{7:040x}")
        self.assertFalse(result["closed"]["poll"])
        self.assertTrue(result["closed"]["immutable"])
        self.assertIn(
            "/refs/heads/autoresearch-acts-seeding/running/orchestration-files/campaign-status.json",
            result["openUrl"],
        )
        self.assertIn(
            f"/{7:040x}/orchestration-files/campaign-status.json",
            result["closedUrl"],
        )

    def test_snapshot_fetch_uses_canonical_path_then_legacy_404_fallback(self) -> None:
        pulls = [
            self.pull(9, "autoresearch-acts-seeding/running", "2026-08-27T12:00:00Z"),
            self.pull(
                8,
                "autoresearch-acts-seeding/completed",
                "2026-08-26T12:00:00Z",
                state="closed",
            ),
        ]
        result = self.run_discovery_javascript(
            f"const campaigns = sortCampaigns({json.dumps(pulls)});"
            "const open = campaignFetchSource(campaigns.find((item) => item.state === 'open'));"
            "const closed = campaignFetchSource(campaigns.find((item) => item.state === 'closed'));"
            "const oldDeepLink = campaignFetchSource(directCampaign('autoresearch-acts-seeding/old'));"
            "const requests = [];"
            "const canonical = await fetchCampaignSnapshot(open, async (url, options) => {"
            "  requests.push({url, options}); return {ok: true, status: 200};"
            "}, 123);"
            "const legacy = await fetchCampaignSnapshot(closed, async (url, options) => {"
            "  requests.push({url, options});"
            "  return url.includes('/orchestration-files/') ? {ok: false, status: 404} : {ok: true, status: 200};"
            "}, 456);"
            "const deepLink = await fetchCampaignSnapshot(oldDeepLink, async (url, options) => {"
            "  requests.push({url, options});"
            "  return url.includes('/orchestration-files/') ? {ok: false, status: 404} : {ok: true, status: 200};"
            "}, 789);"
            "console.log(JSON.stringify({canonical, legacy, deepLink, requests}));"
        )
        self.assertEqual(
            result["canonical"]["statusPath"],
            "orchestration-files/campaign-status.json",
        )
        self.assertEqual(result["legacy"]["statusPath"], "campaign-status.json")
        self.assertEqual(result["deepLink"]["statusPath"], "campaign-status.json")
        self.assertEqual(len(result["requests"]), 5)
        self.assertIn("/orchestration-files/campaign-status.json?_=123", result["requests"][0]["url"])
        self.assertIn(f"/{8:040x}/orchestration-files/campaign-status.json?_=456", result["requests"][1]["url"])
        self.assertIn(f"/{8:040x}/campaign-status.json?_=456", result["requests"][2]["url"])
        self.assertIn(
            "/refs/heads/autoresearch-acts-seeding/old/campaign-status.json?_=789",
            result["requests"][4]["url"],
        )
        self.assertTrue(
            all(request["options"]["credentials"] == "omit" for request in result["requests"])
        )

    def test_snapshot_fetch_does_not_mask_non_404_canonical_errors(self) -> None:
        result = self.run_discovery_javascript(
            "const source = campaignFetchSource(directCampaign('autoresearch-acts-seeding/old'));"
            "const requests = [];"
            "const fetched = await fetchCampaignSnapshot(source, async (url) => {"
            "  requests.push(url); return {ok: false, status: 500};"
            "}, 123);"
            "console.log(JSON.stringify({status: fetched.response.status, requests}));"
        )
        self.assertEqual(result["status"], 500)
        self.assertEqual(len(result["requests"]), 1)
        self.assertIn("/orchestration-files/campaign-status.json", result["requests"][0])

    def test_dashboard_ranks_three_fastest_completed_non_genesis_attempts(self) -> None:
        def attempt(candidate: str, state: str, seeding_ms: float | None) -> dict:
            return {
                "candidate": candidate,
                "state": state,
                "timed_seeding_time_per_event_ms": seeding_ms,
            }

        attempts = [
            attempt("Genesis", "completed", 1),
            attempt("Fourth", "completed", 14),
            attempt("Third", "completed", 13),
            attempt("Running", "running", 2),
            attempt("First", "completed", 10),
            attempt("Missing", "completed", None),
            attempt("Second", "completed", 11),
        ]
        result = self.run_discovery_javascript(
            "const leaders = topSeedingAttempts("
            f"{json.dumps(attempts)}"
            ").map((attempt) => attempt.candidate);"
            "const comparison = seedingComparison("
            "{timed_seeding_time_per_event_ms: 90},"
            "{timed_seeding_time_per_event_ms: 100}"
            ");"
            "const humanized = humanizeCandidateName('DoubletBinaryRadiusWindow');"
            "console.log(JSON.stringify({leaders, comparison, humanized}));"
        )
        self.assertEqual(result["leaders"], ["First", "Second", "Third"])
        self.assertEqual(result["comparison"]["deltaMs"], -10)
        self.assertEqual(result["comparison"]["percentage"], -10)
        self.assertEqual(result["humanized"], "Doublet Binary Radius Window")

    def test_dashboard_timestamp_formatter_is_browser_compatible(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is required for dashboard JavaScript tests")
        html = self.dashboard_html()
        formatter = "function formatInstant" + html.split(
            "function formatInstant", 1
        )[1].split("function formatRelative", 1)[0]
        result = subprocess.run(
            [
                "node",
                "-e",
                formatter
                + "console.log(formatInstant('2026-08-27T12:00:00Z'));",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2026", result.stdout)
        self.assertNotIn("Unavailable", result.stdout)

    def test_dashboard_update_chip_is_only_visible_for_running_campaigns(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is required for dashboard JavaScript tests")
        html = self.dashboard_html()
        renderer = "function renderFreshness" + html.split(
            "function renderFreshness", 1
        )[1].split("function safeLink", 1)[0]
        result = subprocess.run(
            [
                "node",
                "-e",
                "const element = {};"
                "const document = {getElementById: () => element};"
                "const activeCampaign = null;"
                "const freshnessState = () => ({className: 'warn'});"
                "const formatRelative = () => '8m ago';"
                + renderer
                + "renderFreshness({generated_at: 'x'}, {state: 'open'});"
                "const running = {...element};"
                "renderFreshness({generated_at: 'x'}, {state: 'closed'});"
                "console.log(JSON.stringify({running, completed: {...element}}));",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = json.loads(result.stdout)
        self.assertEqual(rendered["running"]["textContent"], "Update · 8m ago")
        self.assertFalse(rendered["running"]["hidden"])
        self.assertTrue(rendered["completed"]["hidden"])

    def test_dashboard_html_has_empty_stale_error_and_interactive_essentials(self) -> None:
        now = datetime(2026, 8, 27, 12, tzinfo=UTC)
        self.assertEqual(freshness_state("2026-08-27T11:59:00Z", now), "fresh")
        self.assertEqual(freshness_state("2026-08-27T11:50:00Z", now), "aging")
        self.assertEqual(freshness_state("2026-08-27T11:40:00Z", now), "stale")

        html = self.dashboard_html()

        for essential in (
            "ACTS Seeding Live Campaign",
            'id="empty-state"',
            'id="fetch-error"',
            "Showing the last good snapshot",
            "max-width: 1920px;",
            "height: 615px;",
            "overflow: hidden;",
            "#chart { width: 100%; height: 100%; }",
            "#chart-frame { height: 510px; }",
            "autosize: true",
            "function renderComparisonChart(snapshot)",
            "function comparisonPoints(snapshot)",
            "const POLL_INTERVAL_MS = 60000;",
            "cache: 'no-store'",
            "credentials: 'omit'",
            'id="campaign-select"',
            "api.github.com/repos/${REPOSITORY}/pulls?state=all",
            "function sortCampaigns(pulls)",
            "function selectInitialCampaign(campaigns, deepLinkRef)",
            "function campaignFetchSource(campaign)",
            "function safeRef(raw)",
            "function freshnessState(snapshot)",
            "function campaignProgressModel(snapshot)",
            "function renderCampaignProgress(snapshot)",
            "Major candidates",
            "Minor candidates",
            "Combination candidates",
            "Status unavailable. This campaign may predate campaign-status v1.",
            "if (source?.poll",
        ):
            self.assertIn(essential, html)
        for removed_control in (
            'id="campaign-form"',
            'id="campaign-ref"',
            'id="load-button"',
            'id="discovery-note"',
            'id="campaign-name"',
            'id="campaign-branch"',
            "Attempt history",
            "<span>Mechanism</span>",
            "cell('Mechanism'",
            'aria-label="Campaign attempts"',
            'id="attempts"',
            'id="history-empty"',
            "function renderHistory(",
            ".attempt-detail",
            'id="phase"',
            'id="current-candidate"',
            'id="mechanism"',
            'id="controlled-stage"',
            'id="median-duration"',
            'id="median-basis"',
            'id="eta-basis"',
            'id="last-update"',
            'id="links-heading"',
            'id="campaign-links"',
            'id="issues-section"',
            'id="issues-heading"',
            'id="issues"',
            'id="genesis-result"',
            'id="efficiency-result"',
            'class="report-link"',
            "Open results report",
            'id="pareto-heading"',
            'id="corner-overlays"',
            "corner-badge",
            "Current two-objective Pareto front",
            "Lower X and higher Y are better. Select a point to open its record.",
            "Timed seeding time/event (ms) · lower is better",
            "Particle ambiguity efficiency · higher is better",
            "Timed seeding is minimized. Particle ambiguity efficiency is maximized.",
            "timeZoneName: 'short'",
            "Public Development progress on the two controlled objectives.",
            "Campaigns are sorted newest to oldest.",
        ):
            self.assertNotIn(removed_control, html)
        self.assertIn("campaignSelect.addEventListener('change'", html)
        self.assertIn("if (selected) selectCampaign(selected);", html)
        self.assertIn("<h2>ACTS Seeding Campaign</h2>", html)
        self.assertIn("campaign?.state !== 'open'", html)
        self.assertIn("element.hidden = true", html)
        self.assertIn("Update · ${formatRelative(snapshot.generated_at)}", html)
        self.assertNotIn("Aging ·", html)
        self.assertNotIn("Stale ·", html)
        self.assertNotIn("Final ·", html)
        self.assertIn("`${state} · ACTS Seeding Campaign", html)
        self.assertIn("<h2 id=\"results-heading\">Promising Early Results</h2>", html)
        self.assertIn('id="seeding-leaders"', html)
        self.assertIn("function renderSeedingLeaders(snapshot)", html)
        self.assertIn("name.className = 'card-name'", html)
        self.assertIn(".card-name {", html)
        self.assertIn("function humanizeCandidateName(value)", html)
        self.assertIn("const commitUrl = safeLink(result.links?.commit)", html)
        self.assertIn("document.createElement(commitUrl ? 'a' : 'div')", html)
        self.assertIn("function seedingComparison(result, genesis)", html)
        self.assertIn("formatSigned(comparison.deltaMs)", html)
        self.assertIn(".slice(0, 3)", html)
        self.assertEqual(html.count("fetch(PULLS_API_URL"), 1)
        polling = html[html.index("setInterval(() => {") :]
        self.assertNotIn("PULLS_API_URL", polling)
        self.assertNotIn("discoverCampaigns", polling)
        self.assertNotIn("full-chain time", html.lower())
        self.assertNotIn("timed_total_time_per_event_ms", html)

    def test_dashboard_chart_matches_interactive_report_visual_contract(self) -> None:
        dashboard = self.dashboard_html()
        report_template = (
            PROJECT_ROOT / "orchestration-files" / "visualizations" / "pareto.py"
        ).read_text(encoding="utf-8")
        for shared_contract in (
            "rgba(34,197,94,0.14)",
            "rgba(239,68,68,0.14)",
            "rgba(234,179,8,0.14)",
            "mode: 'markers', type: 'scatter', name: 'Candidates'",
            "margin: { l: 80, r: 30, t: 45, b: 55 }",
            "legend: { orientation: 'h', x: 0, y: 1.12",
            "paper_bgcolor: '#111827', plot_bgcolor: '#0b1120'",
        ):
            self.assertIn(shared_contract, dashboard)
            self.assertIn(shared_contract, report_template)


if __name__ == "__main__":
    unittest.main()
