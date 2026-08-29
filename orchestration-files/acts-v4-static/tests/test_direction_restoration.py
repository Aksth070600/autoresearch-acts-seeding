from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1]
if str(MODULE) not in sys.path:
    sys.path.insert(0, str(MODULE))

from schema import canonical_json_bytes  # noqa: E402


class ExactDirectionRestorationTests(unittest.TestCase):
    def test_overlay_is_content_addressed_and_grants_only_narrow_friendship(self) -> None:
        manifest_path = MODULE / "overlay-manifest.json"
        raw_manifest = manifest_path.read_bytes()
        manifest = json.loads(raw_manifest)
        self.assertEqual(raw_manifest, canonical_json_bytes(manifest))

        patch = manifest["patch"]
        patch_bytes = (MODULE / patch["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(patch_bytes).hexdigest(), patch["sha256"])

        particle_entry = next(
            entry
            for entry in manifest["modified_files"]
            if entry["path"] == "Fatras/include/ActsFatras/EventData/Particle.hpp"
        )
        self.assertNotEqual(particle_entry["before_sha256"], particle_entry["after_sha256"])
        patch_text = patch_bytes.decode("utf-8")
        self.assertIn(
            "friend struct ActsExamples::OwnedSeedingParticleDirectionRestorer;",
            patch_text,
        )
        self.assertNotIn("setDirectionUnchecked", patch_text)
        self.assertNotIn("setDirectionWithoutNormalization", patch_text)

    def test_reader_restores_validated_bits_without_public_normalizing_setter(self) -> None:
        source = (MODULE / "cpp/src/OwnedSeedingDataset.cpp").read_text(encoding="utf-8")
        accessor = source.index("struct OwnedSeedingParticleDirectionRestorer")
        anonymous_namespace = source.index("namespace {", accessor)
        self.assertIn("particle.m_direction = direction;", source[accessor:anonymous_namespace])

        restore_begin = source.index("SimParticleState restoreState(")
        restore_end = source.index("\n}\n\n}  // namespace", restore_begin)
        restore = source[restore_begin:restore_end]
        self.assertNotIn("state.setDirection(", restore)
        self.assertIn(
            "OwnedSeedingParticleDirectionRestorer::restoreValidated(", restore
        )
        self.assertIn("sameBits(state.direction()[component]", restore)

        read_begin = source.index("OwnedSeedingDatasetReader::read(")
        validation = source.index("validateAndHash(payload", read_begin)
        reconstruction = source.index("restoreState(", validation)
        self.assertLess(validation, reconstruction)


if __name__ == "__main__":
    unittest.main()
