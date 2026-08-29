from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401
from pilot_record import calibrate
from schema import CANONICAL_PROTOCOL_ID, ManifestError, canonical_json_bytes


def result_fixture(timing: int) -> dict:
    digest = "3" * 64
    return {
        "schema": "acts-seeding-v4-owned-static-result-v2",
        "protocol_revision": 2,
        "qualification_only": False,
        "protocol_id": CANONICAL_PROTOCOL_ID,
        "dataset_id": "acts-seeding-v4-owned-static-test-dataset",
        "events": 50,
        "threads": 1,
        "process_exit_status": 0,
        "fpe": {"observed_unmasked": 0},
        "static_process_gate": {"passed": True},
        "candidate_binding": None,
        "input_event_hashes": [digest] * 50,
        "stats": {
            "nTotalParticles": 10,
            "nTotalMatchedParticles": 9,
            "nTotalTracks": 20,
            "nTotalMatchedTracks": 18,
            "nTotalFakeTracks": 1,
            "nTotalDuplicateTracks": 2,
        },
        "identities": {
            "manifest_sha256": digest,
            "payload_sha256": digest,
            "dataset_source_manifest_sha256": digest,
            "dataset_build_manifest_sha256": digest,
            "overlay_manifest_sha256": digest,
        },
        "diagnostics": {"ordered_diagnostics_sha256": digest},
        "timing": {"per_event_nanoseconds": timing},
    }


class PilotCalibrationTests(unittest.TestCase):
    def test_rejects_candidate_binding_in_first_genesis_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for index in range(5):
                value = result_fixture(100 + index)
                if index == 0:
                    value["candidate_binding"] = {"proposal_sha256": "4" * 64}
                path = root / f"result-{index}.json"
                path.write_bytes(canonical_json_bytes(value))
                paths.append(path)

            with self.assertRaisesRegex(
                ManifestError, "cannot contain a candidate binding"
            ):
                calibrate(paths)

            first = json.loads(paths[0].read_text(encoding="utf-8"))
            first["candidate_binding"] = None
            paths[0].write_bytes(canonical_json_bytes(first))
            calibration = calibrate(paths)
            self.assertEqual(calibration["protocol_revision"], 2)
            self.assertEqual(
                calibration["schema"],
                "acts-v4-owned-static-genesis-calibration-v2",
            )


if __name__ == "__main__":
    unittest.main()
