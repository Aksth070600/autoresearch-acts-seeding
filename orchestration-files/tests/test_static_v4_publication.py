import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from static_v4_public_dashboard import render  # noqa: E402


class StaticV4PublicCampaignTests(unittest.TestCase):
    def status(self):
        return {
            "schema": "acts-v4-owned-static-continuous-status-v1",
            "campaign": {
                "campaign_id": "acts-v4-owned-static-continuous-20260829t185722z-fm",
                "control_id": "c" * 64,
                "branch": "fm/acts-v4-continuous-campaign",
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
            "attempts": [
                {
                    "slot": 1,
                    "candidate": "CoreBatchMaterializationV4C",
                    "classification": "major",
                    "mechanism_key": "v4c-core-batch-spacepoint-materialization",
                    "status": "passed",
                    "timing": {"per_event_nanoseconds": 295485000},
                    "stats": {
                        "nTotalMatchedParticles": 57398,
                        "nTotalParticles": 58310,
                        "nTotalFakeTracks": 26451,
                        "nTotalDuplicateTracks": 586907,
                        "nTotalTracks": 1065071,
                    },
                    "scientific_classification": {
                        "timing": {"label": "confidently faster"},
                        "overall": "valid improvement",
                    },
                    "latency": {
                        "build_seconds": "86.127670679",
                        "queue_to_immutable_record_seconds": "251.511444851",
                    },
                    "resources": {"wall_seconds": "76.80", "peak_rss_kb": 2121648},
                    "implementation_commit": "1" * 40,
                    "loaded_dso_manifest_sha256": "2" * 64,
                },
                {
                    "slot": 2,
                    "candidate": "CandidateInlineStorageV4C",
                    "classification": "major",
                    "mechanism_key": "v4c-candidate-inline-bounded-storage",
                    "status": "passed",
                    "timing": {"per_event_nanoseconds": 295884000},
                    "stats": {
                        "nTotalMatchedParticles": 57398,
                        "nTotalParticles": 58310,
                        "nTotalFakeTracks": 26451,
                        "nTotalDuplicateTracks": 586907,
                        "nTotalTracks": 1065071,
                    },
                    "scientific_classification": {
                        "timing": {"label": "confidently faster"},
                        "overall": "valid improvement",
                    },
                    "latency": {
                        "build_seconds": "87.486383499",
                        "queue_to_immutable_record_seconds": "253.036802506",
                    },
                    "resources": {"wall_seconds": "78.30", "peak_rss_kb": 2124800},
                    "implementation_commit": "3" * 40,
                    "loaded_dso_manifest_sha256": "4" * 64,
                },
            ],
            "corrections": [],
        }

    def test_trusted_public_dashboard_shows_exact_active_v4_identity_and_records(self):
        output = render(self.status(), deployed_commit="f" * 40)
        self.assertIn("acts-v4-owned-static-continuous-20260829t185722z-fm", output)
        self.assertIn("CoreBatchMaterializationV4C", output)
        self.assertIn("CandidateInlineStorageV4C", output)
        self.assertIn("295.485000", output)
        self.assertIn("Empirical noise envelope", output)
        self.assertIn("not a confidence level", output)
        self.assertIn("c" * 64, output)
        self.assertIn("f" * 40, output)
        self.assertIn("regular merge commit, never squash", output)
        self.assertIn('id="metric-select"', output)
        self.assertIn('id="metric-chart"', output)
        self.assertIn('class="composition-grid"', output)
        self.assertIn('class="chart-point"', output)
        self.assertIn('class="finish-button"', output)
        self.assertIn("CoreBatchMaterializationV4C", output)
        self.assertNotIn("<script src=", output)
        self.assertNotIn('rel="stylesheet"', output)

    def test_generated_dashboard_inline_javascript_is_syntax_valid(self):
        if shutil.which("node") is None:
            self.skipTest("node is required")
        output = render(self.status(), deployed_commit="f" * 40)
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

    def test_pages_workflow_stays_on_trusted_main_and_fetches_only_campaign_data(self):
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "reports.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("active_campaign_ref:", workflow)
        self.assertIn("active_campaign_commit:", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn(
            "ACTIVE_CAMPAIGN_REF: ${{ inputs.active_campaign_ref }}", workflow
        )
        self.assertIn(
            "ACTIVE_CAMPAIGN_COMMIT: ${{ inputs.active_campaign_commit }}", workflow
        )
        self.assertIn('git fetch --no-tags origin "$ACTIVE_CAMPAIGN_REF"', workflow)
        self.assertIn("static_v4_public_dashboard.py", workflow)
        self.assertIn("--output build/site/campaign/index.html", workflow)
        self.assertNotIn("ref: ${{ inputs.active_campaign_ref }}", workflow)
        self.assertNotIn("python3 /tmp/", workflow)


if __name__ == "__main__":
    unittest.main()
