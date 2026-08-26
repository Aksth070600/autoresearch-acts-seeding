import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
REPORT = PROJECT_ROOT / "orchestration-files" / "report.py"
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from protocol import current_protocol  # noqa: E402
from report import build_report, load_records  # noqa: E402


class ReportPreviewTests(unittest.TestCase):
    def run_report(self, records: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(REPORT),
                "--records",
                str(records),
                "--output",
                str(output),
                "--dataset",
                "all",
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_empty_reset_writes_placeholder_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records"
            records.mkdir()
            output = root / "site"

            result = self.run_report(records, output)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / ".nojekyll").is_file())
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("No protocol-compatible summaries yet", index)
            self.assertIn('"rows":[]', index)

    @staticmethod
    def summary(candidate: str, category: str, time: float, efficiency: float) -> dict:
        run_metrics = {
            "timing_total": {"time_per_event_ms": time},
            "performance": {"ambiguity_resolution": {"efficiency_particles": efficiency}},
        }
        repetitions = [
            {"repetition": number, "status": "passed", "run_metrics": run_metrics}
            for number in (1, 2, 3)
        ]
        return {
            "candidate_name": candidate,
            "category": category,
            "status": "passed",
            "baseline": candidate == "Genesis",
            "protocol_id": "acts-seeding-v2",
            "protocol": current_protocol(),
            "started_at": "2026-08-26T12:00:00+00:00",
            "stages": [
                {
                    "comparison": "clean",
                    "metrics_mode": "none",
                    "events": 10,
                    "status": "passed",
                    "run_metrics": run_metrics,
                }
            ],
            "timed_comparison": {
                "aggregation": "median",
                "repetition_count": 3,
                "required_repetitions": 3,
                "events": 10,
                "complete": True,
                "repetitions": repetitions,
                "median_run_metrics": run_metrics,
                "median_resource_metrics": {},
            },
        }

    def test_genesis_report_averages_only_genesis_and_keeps_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            for name, category, time, efficiency in (
                ("20260826T120000000000Z-Genesis", "Development", 100.0, 0.90),
                ("20260826T130000000000Z-Genesis", "Development", 120.0, 0.94),
                ("20260826T140000000000Z-Candidate", "Development", 80.0, 0.80),
            ):
                folder = records / category / name
                folder.mkdir(parents=True)
                (folder / "summary.json").write_text(
                    json.dumps(self.summary(name.split("-")[-1], category, time, efficiency)),
                    encoding="utf-8",
                )

            rows = load_records(records, "development")
            report = build_report(rows, "Genesis", "development")
            genesis = [row for row in report["rows"] if row["candidate"] == "Genesis"]
            candidates = [row for row in report["rows"] if row["candidate"] == "Candidate"]

            self.assertEqual(len(genesis), 1)
            self.assertEqual(genesis[0]["sample_count"], 2)
            self.assertEqual(genesis[0]["metrics"]["timed_total_time_per_event_ms"], 110.0)
            self.assertAlmostEqual(
                genesis[0]["metrics"]["timed_ambiguity_particle_efficiency"], 0.92
            )
            self.assertEqual(
                [item["record"] for item in genesis[0]["provenance"]],
                [
                    "Development/20260826T120000000000Z-Genesis/summary.json",
                    "Development/20260826T130000000000Z-Genesis/summary.json",
                ],
            )
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["metrics"]["timed_total_time_per_event_ms"], 80.0)
            self.assertEqual(report["genesis_aggregation"]["sample_count"], 2)

    def test_all_dataset_documents_cross_category_genesis_aggregation(self) -> None:
        rows = [
            {
                "candidate": "Genesis",
                "category": "Development",
                "record": "Development/Genesis-a/summary.json",
                "commit": "a",
                "metrics": {"timed_total_time_per_event_ms": 100.0},
            },
            {
                "candidate": "Genesis",
                "category": "Evaluation",
                "record": "Evaluation/Genesis-b/summary.json",
                "commit": "b",
                "metrics": {"timed_total_time_per_event_ms": 120.0},
            },
        ]

        report = build_report(rows, "Genesis", "all")

        self.assertIn("Development and Evaluation", report["dataset_description"])
        self.assertEqual(report["genesis_aggregation"]["sample_count"], 2)
        self.assertEqual(
            report["rows"][0]["metrics"]["timed_total_time_per_event_ms"], 110.0
        )

    def test_existing_summary_keeps_strict_metric_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = root / "records" / "Development" / "Genesis"
            records.mkdir(parents=True)
            (records / "summary.json").write_text(
                json.dumps(
                    {
                        "candidate_name": "Genesis",
                        "category": "Development",
                        "status": "passed",
                        "protocol_id": "acts-seeding-v2",
                        "protocol": {
                            "id": "acts-seeding-v2",
                            "acts_version": "v46.5.0",
                            "dataset": "ttbar_pu200",
                            "execution_target": "HEPP02",
                            "threads": 1,
                            "seed": 42,
                            "pileup": 200,
                            "development_events": 10,
                            "evaluation_events": 50,
                            "timed_repetitions": 3,
                            "timed_aggregation": "median",
                            "expected_unmasked_fpe_handling": "accept only after every requested event completed",
                        },
                        "stages": [],
                    }
                ),
                encoding="utf-8",
            )
            output = root / "site"

            result = self.run_report(records.parents[1], output)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("x metric not found", result.stderr)
            self.assertFalse((output / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
