import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from static_v4_public_dashboard import render  # noqa: E402
from visualizations.campaign import PLOTLY_SCRIPT_URL  # noqa: E402


class ArtifactParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes = set()
        self.ids = set()
        self.script_sources = []
        self.hrefs = []
        self.attempt_count = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.classes.update(attributes.get("class", "").split())
        if "id" in attributes:
            self.ids.add(attributes["id"])
        if tag == "script" and "src" in attributes:
            self.script_sources.append(attributes["src"])
        if tag == "a" and "href" in attributes:
            self.hrefs.append(attributes["href"])
        if attributes.get("id") == "dashboard":
            self.attempt_count = int(attributes["data-attempt-count"])


class StaticV4PublicCampaignTests(unittest.TestCase):
    def status(self):
        genesis_interval = {
            "lower": {"numerator": 297004000, "denominator": 1},
            "upper": {"numerator": 298800000, "denominator": 1},
        }
        candidate_interval = {
            "lower": {"numerator": 294500000, "denominator": 1},
            "upper": {"numerator": 296500000, "denominator": 1},
        }
        attempts = []
        for slot, candidate, mechanism, timing, commit, rss in (
            (
                1,
                "CoreBatchMaterializationV4C",
                "v4c-core-batch-spacepoint-materialization",
                295485000,
                "1" * 40,
                2121648,
            ),
            (
                2,
                "CandidateInlineStorageV4C",
                "v4c-candidate-inline-bounded-storage",
                295884000,
                "3" * 40,
                2124800,
            ),
        ):
            attempts.append(
                {
                    "slot": slot,
                    "record_path": f"records/Development/slot-{slot}/summary.json",
                    "candidate": candidate,
                    "classification": "major",
                    "mechanism_key": mechanism,
                    "status": "passed",
                    "timing": {"per_event_nanoseconds": timing},
                    "stats": {
                        "nTotalMatchedParticles": 57398,
                        "nTotalParticles": 58310,
                        "nTotalFakeTracks": 26451,
                        "nTotalDuplicateTracks": 586907,
                        "nTotalTracks": 1065071,
                    },
                    "scientific_classification": {
                        "timing": {
                            "label": "confidently faster",
                            "candidate_interval_nanoseconds": candidate_interval,
                            "genesis_interval_nanoseconds": genesis_interval,
                        },
                        "efficiency": {
                            "genesis": {"numerator": 28699, "denominator": 29155}
                        },
                        "overall": "valid improvement",
                    },
                    "latency": {
                        "preparation_seconds": "174.473603783",
                        "build_seconds": "86.127670679",
                        "queue_to_immutable_record_seconds": "251.511444851",
                    },
                    "resources": {"wall_seconds": "76.80", "peak_rss_kb": rss},
                    "implementation_commit": commit,
                    "loaded_dso_manifest_sha256": "2" * 64,
                    "proposal": {
                        "changed_symbols": ["Acts::Example::execute"],
                        "derives_from": (
                            {
                                "candidate": "EarlierCandidate",
                                "mechanism_key": "earlier-mechanism",
                                "implementation_commit": "9" * 40,
                            }
                            if slot == 1
                            else None
                        ),
                        "combination_provenance": None,
                    },
                }
            )
        return {
            "schema": "acts-v4-owned-static-continuous-status-v1",
            "generated_at": "2026-08-29T20:12:32Z",
            "campaign": {
                "campaign_id": "acts-v4-owned-static-continuous-20260829t185722z-fm",
                "control_id": "c" * 64,
                "branch": "fm/acts-v4-continuous-campaign",
                "started_at": "2026-08-29T18:57:22Z",
                "platform_commit": "c72c1a32d61858eaad05b0f6f19c712d0c53f2ba",
                "scientific_genesis_commit": "5ed3b47329ceda4edaab48b1efc3c5635f361a30",
                "acts_commit": "34edd48852f766e1b9d94d3dc996e27476339f1b",
                "protocol_id": "acts-seeding-v4-owned-static",
                "protocol_revision": 2,
                "dataset_id": "acts-seeding-v4-owned-static-a05ae8663452d52dc2b90e2fa5372091a2cb04feb8cce86646da9f6ccbc2f3fb",
            },
            "calibration": {
                "genesis_per_event_nanoseconds": [
                    297700000,
                    298122000,
                    297266000,
                    298800000,
                    297902000,
                ],
                "median_per_event_nanoseconds": 297902000,
                "median_peak_rss_kb": 2125020,
                "baseline": {
                    "stats": {
                        "nTotalMatchedParticles": 57398,
                        "nTotalParticles": 58310,
                    }
                },
                "relative_empirical_noise_envelope": {
                    "numerator": 449,
                    "denominator": 148951,
                },
            },
            "control": {"state": "open"},
            "scheduler": {"state": "running", "next_category": "minor"},
            "composition": {
                "counts": {"major": 2, "minor": 0, "combination": 0},
                "completed_blocks": 0,
            },
            "current_attempt": None,
            "attempts": attempts,
            "corrections": [],
        }

    def output(self):
        first = datetime(2026, 8, 29, 19, 19, 49, tzinfo=timezone.utc)
        return render(
            self.status(),
            deployed_commit="f" * 40,
            completion_times={1: first, 2: first + timedelta(minutes=6, seconds=34)},
        )

    def test_generated_artifact_has_accepted_visual_structure_and_exact_identity(self):
        output = self.output()
        parser = ArtifactParser()
        parser.feed(output)

        self.assertEqual(parser.attempt_count, 2)
        self.assertEqual(parser.script_sources, [PLOTLY_SCRIPT_URL])
        self.assertTrue(all(url.startswith("https://") for url in parser.hrefs))
        for required_class in (
            "controls",
            "finish-control",
            "identity-row",
            "progress-grid",
            "timing-grid",
            "results-grid",
            "card",
            "corner-badge",
        ):
            self.assertIn(required_class, parser.classes)
        for required_id in (
            "campaign-select",
            "finish-control",
            "finish-identity",
            "dashboard",
            "baseline-heading",
            "chart-frame",
            "chart",
            "corner-overlays",
        ):
            self.assertIn(required_id, parser.ids)

        self.assertIn("Running · ACTS Seeding Campaign · Aug 29, 2026", output)
        self.assertIn("acts-v4-owned-static-continuous-20260829t185722z-fm", output)
        self.assertIn("Core Batch Materialization", output)
        self.assertIn("295.485 ms", output)
        self.assertIn("Time per experiment", output)
        self.assertIn("6m 34s", output)
        self.assertIn("449/148951", output)
        self.assertNotIn("Captain visual review", output)
        self.assertNotIn('rel="stylesheet"', output)

    def test_generated_chart_payload_preserves_all_exact_v4_record_data(self):
        output = self.output()
        match = re.search(
            r"const CAMPAIGN = (.*?);\nconst plotEmpty", output, re.DOTALL
        )
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))

        self.assertEqual(
            payload["campaign"]["protocol_id"], "acts-seeding-v4-owned-static"
        )
        self.assertEqual(payload["campaign"]["protocol_revision"], 2)
        self.assertEqual(len(payload["attempts"]), 2)
        first = payload["attempts"][0]
        self.assertEqual(first["candidate"], "CoreBatchMaterializationV4C")
        self.assertEqual(first["timing_ms"], 295.485)
        self.assertEqual(first["efficiency"], 57398 / 58310)
        self.assertEqual(first["fake_rate"], 26451 / 1065071)
        self.assertEqual(first["duplicate_rate"], 586907 / 1065071)
        self.assertEqual(first["latency"]["queue_to_record_seconds"], 251.511444851)
        self.assertEqual(
            first["mechanism_key"], "v4c-core-batch-spacepoint-materialization"
        )
        self.assertEqual(first["lineage"][0]["candidate"], "EarlierCandidate")
        self.assertEqual(
            first["commit_url"],
            f"https://github.com/Aksth070600/autoresearch-acts-seeding/commit/{'1' * 40}",
        )
        self.assertEqual(payload["genesis"]["empirical_envelope"], "449/148951")

        for visual_contract in (
            "mode:'markers',type:'scatter',name:'Candidates'",
            "pointSize",
            "Decision: ${decision}",
            "rgba(34,197,94,0.14)",
            "rgba(239,68,68,0.14)",
            "rgba(234,179,8,0.14)",
            "x0:0,x1:1,xref:'paper',y0:gy,y1:gy",
            "paper_bgcolor:'#111827',plot_bgcolor:'#0b1120'",
        ):
            self.assertIn(visual_contract, output)

    def test_generated_dashboard_inline_javascript_is_syntax_valid(self):
        if shutil.which("node") is None:
            self.skipTest("node is required")
        output = self.output()
        scripts = re.findall(r"<script>(.*?)</script>", output, re.DOTALL)
        self.assertEqual(len(scripts), 1)
        result = subprocess.run(
            ["node", "--check", "-"],
            input=scripts[0],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_public_dashboard_rejects_v3_or_wrong_static_dataset(self):
        status = self.status()
        status["campaign"]["protocol_id"] = "acts-seeding-v3"
        with self.assertRaisesRegex(ValueError, "exact revision-2"):
            render(status, deployed_commit="f" * 40)

    def test_ordinary_main_publication_generates_terminal_archive_in_both_entries(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "reports.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("push:\n    branches:\n      - main", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("python3 orchestration-files/report.py", workflow)
        self.assertIn("path: build/site", workflow)
        self.assertNotIn("active_campaign_ref", workflow)
        self.assertNotIn("ACTIVE_CAMPAIGN", workflow)
        self.assertNotIn("git fetch", workflow)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "orchestration-files" / "report.py"),
                    "--dataset",
                    "development",
                    "--output",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            artifacts = {
                "report": (output / "index.html").read_text(encoding="utf-8"),
                "campaign": (output / "campaign" / "index.html").read_text(
                    encoding="utf-8"
                ),
            }

        for entry, artifact in artifacts.items():
            with self.subTest(entry=entry):
                self.assertIn(
                    "acts-v4-owned-static-continuous-20260829t185722z-fm",
                    artifact,
                )
                self.assertIn('data-attempt-count="128"', artifact)
                self.assertIn("64 major / 32 minor / 32 combination", artifact)
                self.assertIn("297.902 ms/event", artifact)
                self.assertIn("270.916 / 281.309 ms/event", artifact)
                self.assertIn("Completed", artifact)
                self.assertIn("invalid: process crashed", artifact)
                self.assertIn("GridSelectorRejectionHintV4C", artifact)
                self.assertIn("CoreSpacePointBufferReuseV4C", artifact)
                self.assertIn("queue-record", artifact)
                self.assertIn("Immutable record", artifact)
                self.assertIn("284ffffbc7863578435a4a5b40aa52c708f1481b", artifact)

        # The historical interactive report remains an exact v3 ranking. The
        # v4 archive is a separate section, never a row in the REPORT payload.
        report_payload = re.search(
            r"const REPORT = (.*?);\nconst DEFAULTS", artifacts["report"], re.DOTALL
        )
        self.assertIsNotNone(report_payload)
        payload = json.loads(report_payload.group(1))
        self.assertTrue(payload["rows"])
        self.assertEqual(
            {row["protocol_id"] for row in payload["rows"]}, {"acts-seeding-v3"}
        )
        self.assertNotIn("terminal_campaign", payload)


if __name__ == "__main__":
    unittest.main()
