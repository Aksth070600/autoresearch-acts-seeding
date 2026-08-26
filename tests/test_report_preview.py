import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
REPORT = PROJECT_ROOT / "orchestration-files" / "report.py"


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
