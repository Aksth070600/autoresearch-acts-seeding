import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "orchestration-files"))

from protocol import current_protocol  # noqa: E402
from record import candidate_directories  # noqa: E402


class RecordLookupTests(unittest.TestCase):
    def test_timestamped_genesis_is_returned_before_legacy_canonical_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = Path(temporary) / "records"
            for name, started_at in (
                ("Genesis", "2026-08-26T12:00:00+00:00"),
                ("20260826T130000000000Z-Genesis", "2026-08-26T13:00:00+00:00"),
                ("20260826T140000000000Z-Genesis", "2026-08-26T14:00:00+00:00"),
            ):
                folder = records / "Development" / name
                folder.mkdir(parents=True)
                (folder / "summary.json").write_text(
                    json.dumps(
                        {
                            "candidate_name": "Genesis",
                            "status": "passed",
                            "protocol_id": "acts-seeding-v2",
                            "protocol": current_protocol(),
                            "started_at": started_at,
                        }
                    ),
                    encoding="utf-8",
                )

            directories = candidate_directories("Genesis", False, records)

            self.assertEqual(
                directories[0].relative_to(records).as_posix(),
                "Development/20260826T140000000000Z-Genesis",
            )
            self.assertEqual(len(directories), 3)


if __name__ == "__main__":
    unittest.main()
