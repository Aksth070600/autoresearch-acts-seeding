from __future__ import annotations

import unittest

from support import ACTS_COMMIT, ACTS_TAG, PROVISIONAL_PROTOCOL_PREFIX

from parse_result import build_result, parse_timing_csv
from schema import ManifestError


def raw_fixture() -> dict:
    digest = "2" * 64
    return {
        "protocol_id": PROVISIONAL_PROTOCOL_PREFIX + "-unit",
        "dataset_id": "owned-static-unit-dataset",
        "event_count": 2,
        "thread_count": 1,
        "completed_event_ids": [0, 1],
        "input_event_hashes": [digest, digest],
        "stats": {
            "nTotalTracks": 10,
            "nTotalMatchedTracks": 9,
            "nTotalFakeTracks": 1,
            "nTotalDuplicateTracks": 2,
            "nTotalParticles": 8,
            "nTotalMatchedParticles": 7,
            "nTotalDuplicateParticles": 1,
            "nTotalFakeParticles": 1,
        },
        "diagnostics": {
            "raw_seed_count": 12,
            "estimated_seed_count": 10,
            "estimated_parameter_count": 10,
            "converted_track_count": 10,
            "matcher_classification_counts": {
                "matched": 7,
                "fake": 1,
                "duplicate": 2,
                "unknown": 0,
            },
            "ordered_diagnostics_sha256": digest,
        },
        "identities": {
            "acts_tag": ACTS_TAG,
            "acts_commit": ACTS_COMMIT,
            "manifest_sha256": digest,
            "payload_sha256": digest,
            "dataset_source_manifest_sha256": digest,
            "dataset_build_manifest_sha256": digest,
            "runtime_source_manifest_sha256": digest,
            "runtime_build_manifest_sha256": digest,
            "overlay_manifest_sha256": digest,
            "loaded_dso_manifest_sha256": "28b828963758703a7b2241af69d42366a3c5c053bae8ae20f7d421c042d636ca",
            "runner_sha256": digest,
        },
        "candidate_binding": None,
        "loaded_dsos": {"lib64/libActsCore.so": digest},
        "expected_unmasked_fpes": 0,
        "root_plots": False,
    }


TIMING = "identifier,time_total_s,time_perevent_s\nAlgorithm:GridTripletSeedingAlgorithm,1.000000000,0.500000000\n"
TIME_V = """\
User time (seconds): 2.00
System time (seconds): 0.10
Elapsed (wall clock) time (h:mm:ss or m:ss): 0:02.20
Maximum resident set size (kbytes): 12345
Exit status: 0
"""
LOG = "Processed 2 events in 2.1s\nNo unmasked FPEs encountered\n"


class ResultTests(unittest.TestCase):
    def test_protocol_revision_two_binds_complete_loaded_dso_closure(self) -> None:
        raw = raw_fixture()
        raw["protocol_revision"] = 2
        raw["loaded_acts_dso_closure"] = {
            "inspection": "/proc/self/maps",
            "complete": True,
            "external_acts_objects_rejected": True,
            "object_count": 1,
        }
        result = build_result(
            raw,
            timing_csv=TIMING,
            time_v=TIME_V,
            process_log=LOG,
            process_exit_status=0,
        )
        self.assertEqual(result["schema"], "acts-seeding-v4-owned-static-result-v2")
        self.assertEqual(result["protocol_revision"], 2)
        self.assertTrue(result["loaded_acts_dso_closure"]["complete"])

        raw["loaded_acts_dso_closure"]["object_count"] = 2
        self.assertRejected(raw=raw)

    def test_emits_exact_pairs_resources_and_stable_hash(self) -> None:
        result = build_result(
            raw_fixture(),
            timing_csv=TIMING,
            time_v=TIME_V,
            process_log=LOG,
            process_exit_status=0,
            total_latency_seconds="42.5",
        )
        self.assertEqual(result["rates"]["particle_efficiency"], {"numerator": 7, "denominator": 8})
        self.assertEqual(result["rates"]["fake_tracks"], {"numerator": 1, "denominator": 10})
        self.assertEqual(result["resources"]["peak_rss_kb"], 12345)
        self.assertEqual(len(result["result_sha256"]), 64)
        repeated = build_result(
            raw_fixture(),
            timing_csv=TIMING,
            time_v=TIME_V,
            process_log=LOG,
            process_exit_status=0,
            total_latency_seconds="42.5",
        )
        self.assertEqual(result, repeated)

    def assertRejected(self, *, raw=None, timing=TIMING, time_v=TIME_V, log=LOG, status=0, total=None) -> None:  # noqa: N802
        with self.assertRaises(ManifestError):
            build_result(
                raw_fixture() if raw is None else raw,
                timing_csv=timing,
                time_v=time_v,
                process_log=log,
                process_exit_status=status,
                total_latency_seconds=total,
            )

    def test_rejects_incomplete_runs_and_unexpected_fpe(self) -> None:
        raw = raw_fixture()
        raw["completed_event_ids"] = [0]
        self.assertRejected(raw=raw)
        self.assertRejected(log="Processed 2 events in 2.1s\nEncountered 1 unmasked FPEs\n")
        self.assertRejected(log="Processed 1 events in 2.1s\nNo unmasked FPEs encountered\n")
        self.assertRejected(status=1)

    def test_rejects_counter_histogram_substitution_shapes(self) -> None:
        raw = raw_fixture()
        raw["stats"]["nTotalParticles"] = 8.0
        self.assertRejected(raw=raw)
        raw = raw_fixture()
        raw["stats"].pop("nTotalMatchedParticles")
        raw["stats"]["trackeff_hist_integral"] = 7
        self.assertRejected(raw=raw)

    def test_rejects_protocol_identity_and_diagnostic_drift(self) -> None:
        raw = raw_fixture()
        raw["protocol_id"] = "acts-seeding-v3"
        self.assertRejected(raw=raw)
        raw = raw_fixture()
        raw["diagnostics"]["converted_track_count"] = 9
        self.assertRejected(raw=raw)
        raw = raw_fixture()
        raw["diagnostics"]["matcher_classification_counts"]["unknown"] = 1
        self.assertRejected(raw=raw)
        raw = raw_fixture()
        raw["diagnostics"]["matcher_classification_counts"]["fake"] = 0
        raw["diagnostics"]["matcher_classification_counts"]["unknown"] = 1
        self.assertRejected(raw=raw)
        raw = raw_fixture()
        raw["stats"]["nTotalTracks"] = 0
        raw["diagnostics"]["converted_track_count"] = 0
        raw["diagnostics"]["estimated_seed_count"] = 0
        raw["diagnostics"]["estimated_parameter_count"] = 0
        raw["diagnostics"]["matcher_classification_counts"] = {
            "matched": 0,
            "fake": 0,
            "duplicate": 0,
            "unknown": 0,
        }
        self.assertRejected(raw=raw)

    def test_accepts_only_sequencer_display_precision_rounding(self) -> None:
        observed = (
            "identifier,time_total_s,time_perevent_s\n"
            "Algorithm:GridTripletSeedingAlgorithm,14.8587,0.297173\n"
        )
        timing = parse_timing_csv(observed, 50)
        self.assertEqual(timing["total_nanoseconds"], 14_858_700_000)
        inconsistent = observed.replace("0.297173", "0.297160")
        with self.assertRaises(ManifestError):
            parse_timing_csv(inconsistent, 50)

    def test_enforces_independent_process_and_total_targets(self) -> None:
        slow_time = TIME_V.replace("0:02.20", "3:00.01")
        self.assertRejected(time_v=slow_time)
        self.assertRejected(total="300.001")
        result = build_result(
            raw_fixture(),
            timing_csv=TIMING,
            time_v=TIME_V,
            process_log=LOG,
            process_exit_status=0,
            total_latency_seconds="299.999",
        )
        self.assertFalse(result["preparation_build_target_waives_other_targets"])


if __name__ == "__main__":
    unittest.main()
