from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

MODULE = Path(__file__).resolve().parents[1]
if str(MODULE) not in sys.path:
    sys.path.insert(0, str(MODULE))

from schema import (  # noqa: E402
    ACTS_COMMIT,
    ACTS_TAG,
    CANONICAL_STREAM_ID,
    MANIFEST_SCHEMA_ID,
    MANIFEST_SCHEMA_VERSION,
    PROVISIONAL_PROTOCOL_PREFIX,
    UNRESOLVED_CAPTAIN_DECISIONS,
)
from semantic import validate_and_hash_event  # noqa: E402


def state(momentum: float = 2.0) -> dict[str, Any]:
    return {
        "position4": [0.0, -0.0, 1.0, 0.0],
        "direction3": [0.0, 0.0, 1.0],
        "absolute_momentum": momentum,
        "proper_time": 0.0,
        "path_in_x0": 0.0,
        "path_in_l0": 0.0,
        "number_of_hits": 10,
        "outcome": 0,
    }


def event_fixture() -> dict[str, Any]:
    p1 = [1, 0, 1, 0, 0]
    p2 = [1, 0, 2, 0, 0]
    return {
        "ordinal": 0,
        "event_id": 0,
        "measurements": [
            {
                "index": 0,
                "geometry_id": 100,
                "subspace_indices": [0, 1],
                "parameters": [1.25, -2.5],
                "covariance": [0.1, 0.01, 0.01, 0.2],
            },
            {
                "index": 1,
                "geometry_id": 101,
                "subspace_indices": [0, 1],
                "parameters": [2.25, 3.5],
                "covariance": [0.3, 0.0, 0.0, 0.4],
            },
        ],
        "space_points": [
            {
                "index": 0,
                "kind": 0,
                "overlap_class": 0,
                "x": 1.0,
                "y": 2.0,
                "z": 3.0,
                "r": 2.2360680103302,
                "time_valid": False,
                "time": 0.0,
                "variance_r": 0.1,
                "variance_z": 0.2,
                "source_links": [{"geometry_id": 100, "measurement_index": 0}],
            },
            {
                "index": 1,
                "kind": 0,
                "overlap_class": 0,
                "x": 2.0,
                "y": 3.0,
                "z": 4.0,
                "r": 3.605551242828369,
                "time_valid": True,
                "time": 0.5,
                "variance_r": 0.2,
                "variance_z": 0.3,
                "source_links": [{"geometry_id": 101, "measurement_index": 1}],
            },
        ],
        "particles": [
            {
                "barcode": p1,
                "pdg": 13,
                "process": 1,
                "charge": -1.0,
                "mass": 0.105,
                "initial": state(),
                "final": state(1.5),
                "selected": True,
            },
            {
                "barcode": p2,
                "pdg": -13,
                "process": 1,
                "charge": 1.0,
                "mass": 0.105,
                "initial": state(),
                "final": state(1.75),
                "selected": False,
            },
        ],
        "measurement_particles": [
            {"ordinal": 0, "measurement_index": 0, "barcode": p1},
            {"ordinal": 1, "measurement_index": 0, "barcode": p1},
            {"ordinal": 2, "measurement_index": 1, "barcode": p2},
        ],
        "particle_measurements": [
            {"ordinal": 0, "barcode": p1, "measurement_index": 0},
            {"ordinal": 1, "barcode": p1, "measurement_index": 0},
            {"ordinal": 2, "barcode": p2, "measurement_index": 1},
        ],
    }


def manifest_fixture(event_count: int = 1) -> dict[str, Any]:
    events = []
    for ordinal in range(event_count):
        event = event_fixture()
        event["ordinal"] = ordinal
        event["event_id"] = ordinal
        events.append(validate_and_hash_event(event, expected_ordinal=ordinal, expected_event_id=ordinal))
    digest = "1" * 64
    return {
        "schema": {
            "id": MANIFEST_SCHEMA_ID,
            "version": MANIFEST_SCHEMA_VERSION,
            "canonical_stream": CANONICAL_STREAM_ID,
        },
        "qualification": {
            "only": True,
            "canonical": False,
            "unresolved_captain_decisions": list(UNRESOLVED_CAPTAIN_DECISIONS),
        },
        "protocol": {
            "id": PROVISIONAL_PROTOCOL_PREFIX + "-unit",
            "prefix": PROVISIONAL_PROTOCOL_PREFIX,
        },
        "dataset": {
            "id": "owned-static-unit-dataset",
            "event_count": event_count,
            "ordered_event_ids": list(range(event_count)),
            "events": events,
        },
        "payload": {
            "file": "payload.root",
            "sha256": digest,
            "size_bytes": 1,
            "root_uuid": "unit-root-uuid",
            "compression": {"algorithm": "lz4", "level": 4},
        },
        "production": {
            "acts": {"tag": ACTS_TAG, "commit": ACTS_COMMIT},
            "project_genesis_commit": None,
            "project_genesis_is_canonical": False,
            "seed": 42,
            "pileup": 200,
            "events": event_count,
            "threads": 1,
            "generator": "Pythia8",
            "hard_process": ["Top:qqbar2ttbar=on"],
            "host": "qualification-host",
            "container_image_sha256": digest,
            "started_at": "2026-08-29T00:00:00Z",
            "finished_at": "2026-08-29T00:00:01Z",
            "exit_status": 0,
            "completed_event_ids": list(range(event_count)),
            "unmasked_fpes": 1,
        },
        "identities": {
            "source_manifest_sha256": digest,
            "build_manifest_sha256": digest,
            "overlay_manifest_sha256": digest,
            "writer_source_sha256": digest,
            "reader_source_sha256": digest,
            "builder_sha256": digest,
            "geometry_tgeo_sha256": digest,
            "geometry_material_sha256": digest,
            "field_sha256": digest,
            "digitization_sha256": digest,
            "pixel_geometry_selection_sha256": digest,
            "seeding_config_sha256": digest,
        },
        "contracts": {
            "truth_payload_scope": "all-simulated-particles",
            "selected_particle_marker": "exact-post-digitization-container",
            "pixel_spacepoint_policy": "ordered-pixel-only-one-index-source-link",
            "static_expected_unmasked_fpes": 0,
            "performance_output": "exact-json-collector-stats",
            "root_plots": False,
            "matcher": {"matching_ratio": 1.0, "double_matching": False},
        },
    }


def copy_fixture() -> dict[str, Any]:
    return copy.deepcopy(event_fixture())
