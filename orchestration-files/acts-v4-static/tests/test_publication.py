from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1]
if str(MODULE) not in sys.path:
    sys.path.insert(0, str(MODULE))

import finalize_dataset  # noqa: E402
from schema import ManifestError  # noqa: E402
from support import manifest_fixture  # noqa: E402


class PublicationTests(unittest.TestCase):
    def test_failed_final_validation_restores_payload_and_removes_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staging = root / "staging"
            destination = root / "dataset"
            staging.mkdir()
            payload = staging / "payload.root"
            payload.write_bytes(b"payload whose draft hash is intentionally wrong")

            manifest = manifest_fixture()
            production = dict(manifest["production"])
            for key in ("exit_status", "completed_event_ids", "unmasked_fpes"):
                production.pop(key)
            draft = {
                "schema": manifest["schema"],
                "qualification": manifest["qualification"],
                "protocol": manifest["protocol"],
                "dataset": manifest["dataset"],
                "payload_transport": manifest["payload"],
                "production_without_process_outcome": production,
                "identities": manifest["identities"],
                "contracts": manifest["contracts"],
            }
            (staging / "production-draft.json").write_text(json.dumps(draft))
            log = root / "generation.log"
            log.write_text(
                "Processed 1 events in 1.0 s (wall clock)\n"
                "No unmasked FPEs encountered\n",
                encoding="utf-8",
            )
            arguments = [
                "finalize_dataset.py",
                "--staging",
                str(staging),
                "--destination",
                str(destination),
                "--process-log",
                str(log),
                "--process-exit-status",
                "0",
            ]
            with patch.object(sys, "argv", arguments), self.assertRaises(ManifestError):
                finalize_dataset.main()

            self.assertEqual(payload.read_bytes(), b"payload whose draft hash is intentionally wrong")
            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".dataset.publish-*")), [])


if __name__ == "__main__":
    unittest.main()
