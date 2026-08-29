from __future__ import annotations

import copy
import math
import unittest

from support import event_fixture

from schema import ManifestError
from semantic import validate_and_hash_event


class SemanticContractTests(unittest.TestCase):
    def test_valid_fixture_is_deterministic_and_preserves_signed_zero(self) -> None:
        fixture = event_fixture()
        first = validate_and_hash_event(fixture, resolvable_geometry_ids={100, 101})
        second = validate_and_hash_event(copy.deepcopy(fixture), resolvable_geometry_ids={100, 101})
        self.assertEqual(first, second)

        fixture["particles"][0]["initial"]["position4"][1] = 0.0
        changed = validate_and_hash_event(fixture)
        self.assertNotEqual(first["section_sha256"]["particles"], changed["section_sha256"]["particles"])

    def assertRejected(self, mutate) -> None:  # noqa: N802 - unittest helper style
        fixture = event_fixture()
        mutate(fixture)
        with self.assertRaises(ManifestError):
            validate_and_hash_event(fixture, resolvable_geometry_ids={100, 101})

    def test_rejects_malformed_csr_equivalents_and_covariance(self) -> None:
        self.assertRejected(lambda event: event["measurements"][0]["parameters"].pop())
        self.assertRejected(lambda event: event["measurements"][0]["covariance"].pop())
        self.assertRejected(lambda event: event["measurements"][0].update(subspace_indices=[1, 0]))
        self.assertRejected(lambda event: event["measurements"][0].update(index=7))

    def test_rejects_non_finite_values_and_variances(self) -> None:
        self.assertRejected(lambda event: event["space_points"][0].update(x=math.nan))
        self.assertRejected(lambda event: event["space_points"][0].update(variance_r=-0.1))
        self.assertRejected(lambda event: event["measurements"][0]["parameters"].__setitem__(0, math.inf))
        self.assertRejected(lambda event: event["particles"][0]["final"].update(absolute_momentum=math.nan))
        self.assertRejected(lambda event: event["particles"][0]["initial"].update(direction3=[math.nan, 0.0, 0.0]))

    def test_rejects_non_unit_particle_directions_before_restoration(self) -> None:
        self.assertRejected(lambda event: event["particles"][0]["initial"].update(direction3=[0.0, 0.0, 0.0]))
        self.assertRejected(lambda event: event["particles"][0]["final"].update(direction3=[2.0, 0.0, 0.0]))

    def test_rejects_source_and_geometry_errors(self) -> None:
        self.assertRejected(lambda event: event["space_points"][0]["source_links"].append({"geometry_id": 100, "measurement_index": 0}))
        self.assertRejected(lambda event: event["space_points"][0]["source_links"][0].update(measurement_index=9))
        self.assertRejected(lambda event: event["space_points"][0]["source_links"][0].update(geometry_id=101))
        self.assertRejected(lambda event: event["measurements"][0].update(geometry_id=999))
        self.assertRejected(lambda event: event["space_points"][0].update(time=1.0))

    def test_rejects_particle_and_truth_errors(self) -> None:
        self.assertRejected(lambda event: event["particles"][1].update(barcode=[1, 0, 1, 0, 0]))
        self.assertRejected(lambda event: event["particles"][0].update(barcode=[2**16, 0, 1, 0, 0]))
        self.assertRejected(lambda event: event["particles"][0].update(pdg=0))
        self.assertRejected(lambda event: event["particles"][0].update(process=5))
        self.assertRejected(lambda event: event["particles"][0]["final"].update(outcome=5))
        self.assertRejected(lambda event: event["particles"].reverse())
        self.assertRejected(lambda event: event["measurement_particles"][0].update(barcode=[1, 0, 99, 0, 0]))
        self.assertRejected(lambda event: event["measurement_particles"][0].update(measurement_index=99))
        self.assertRejected(lambda event: event["measurement_particles"][1].update(ordinal=7))

    def test_rejects_map_inversion_and_multiplicity_differences(self) -> None:
        self.assertRejected(lambda event: event["particle_measurements"].pop())
        self.assertRejected(lambda event: event["particle_measurements"][1].update(measurement_index=1))
        self.assertRejected(lambda event: event["particle_measurements"].reverse())

    def test_rejects_missing_duplicate_or_reordered_events_by_identity(self) -> None:
        with self.assertRaises(ManifestError):
            validate_and_hash_event(event_fixture(), expected_ordinal=1)
        with self.assertRaises(ManifestError):
            validate_and_hash_event(event_fixture(), expected_event_id=1)


if __name__ == "__main__":
    unittest.main()
