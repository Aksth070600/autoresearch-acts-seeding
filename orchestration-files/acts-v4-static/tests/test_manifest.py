from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from support import manifest_fixture

from schema import (
    ManifestError,
    canonical_json_bytes,
    validate_dataset_directory,
    validate_manifest,
)


class ManifestTests(unittest.TestCase):
    def test_accepts_strict_provisional_manifest(self) -> None:
        manifest = manifest_fixture(2)
        self.assertEqual(validate_manifest(manifest, expected_events=2), manifest)

    def test_rejects_protocol_drift_and_old_protocols(self) -> None:
        for protocol in ("acts-seeding-v2", "acts-seeding-v3", "acts-seeding-v4"):
            manifest = manifest_fixture()
            manifest["protocol"]["id"] = protocol
            with self.assertRaises(ManifestError):
                validate_manifest(manifest)

    def test_rejects_policy_selection_and_unknown_fields(self) -> None:
        manifest = manifest_fixture()
        manifest["qualification"]["canonical"] = True
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)
        manifest = manifest_fixture()
        manifest["qualification"]["unresolved_captain_decisions"].pop()
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)
        manifest = manifest_fixture()
        manifest["new_policy"] = "not allowed"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_rejects_missing_duplicate_and_reordered_events(self) -> None:
        manifest = manifest_fixture(2)
        manifest["dataset"]["events"].pop()
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)
        manifest = manifest_fixture(2)
        manifest["dataset"]["ordered_event_ids"] = [0, 0]
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)
        manifest = manifest_fixture(2)
        manifest["dataset"]["events"].reverse()
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def make_directory(self, root: Path) -> dict:
        payload = b"qualification-root-payload"
        payload_hash = hashlib.sha256(payload).hexdigest()
        manifest = manifest_fixture()
        manifest["payload"]["sha256"] = payload_hash
        manifest["payload"]["size_bytes"] = len(payload)
        manifest_bytes = canonical_json_bytes(manifest)
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        (root / "payload.root").write_bytes(payload)
        (root / "manifest.json").write_bytes(manifest_bytes)
        (root / "SHA256SUMS").write_text(
            f"{manifest_hash}  manifest.json\n{payload_hash}  payload.root\n",
            encoding="ascii",
        )
        return manifest

    def test_validates_detached_and_payload_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = self.make_directory(root)
            actual, detached = validate_dataset_directory(root, expected_events=1)
            self.assertEqual(actual, expected)
            self.assertEqual(detached["payload.root"], expected["payload"]["sha256"])

    def test_rejects_tamper_extra_file_and_noncanonical_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_directory(root)
            (root / "payload.root").write_bytes(b"tampered")
            with self.assertRaises(ManifestError):
                validate_dataset_directory(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_directory(root)
            (root / "partial.root").write_bytes(b"partial")
            with self.assertRaises(ManifestError):
                validate_dataset_directory(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.make_directory(root)
            pretty = (str(manifest).replace("'", '"')).encode()
            (root / "manifest.json").write_bytes(pretty)
            digest = hashlib.sha256(pretty).hexdigest()
            lines = (root / "SHA256SUMS").read_text().splitlines()
            lines[0] = f"{digest}  manifest.json"
            (root / "SHA256SUMS").write_text("\n".join(lines) + "\n")
            with self.assertRaises(ManifestError):
                validate_dataset_directory(root)


if __name__ == "__main__":
    unittest.main()
