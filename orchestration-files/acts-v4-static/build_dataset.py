#!/usr/bin/env python3
"""Build a staged qualification payload from the trusted generated ITk chain.

This command never publishes a dataset directory. ``finalize_dataset.py`` must
validate the process log and atomically promote the three-file dataset.
"""

from __future__ import annotations

import argparse
import datetime as dt
import socket
from pathlib import Path

import acts
import acts.examples
import acts.examples.itk
import acts.examples.root
from acts.examples.reconstruction import addSpacePointsMaking
from acts.examples.simulation import (
    ParticleSelectorConfig,
    addDigiParticleSelection,
    addDigitization,
    addFatras,
    addGenParticleSelection,
    addPythia8,
)

from identity import input_identities, source_file_identities, validate_private_build
from pipeline import add_exact_downstream, diagnostics_dict, stats_dict
from schema import (
    ACTS_COMMIT,
    ACTS_TAG,
    CANONICAL_STREAM_ID,
    MANIFEST_SCHEMA_ID,
    MANIFEST_SCHEMA_VERSION,
    PROVISIONAL_PROTOCOL_PREFIX,
    UNRESOLVED_CAPTAIN_DECISIONS,
    ManifestError,
    atomic_write_json,
    sha256_file,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=positive_int, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--geometry-dir", type=Path, required=True)
    parser.add_argument("--private-source", type=Path, required=True)
    parser.add_argument("--private-build", type=Path, required=True)
    parser.add_argument("--identity-dir", type=Path, required=True)
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--compression", choices=("uncompressed", "lz4", "zstd"), required=True)
    parser.add_argument("--compression-level", type=int, required=True)
    parser.add_argument("--container-image-sha256", required=True)
    parser.add_argument("--project-genesis-commit")
    return parser.parse_args()


def event_summary(summary) -> dict:
    return {
        "ordinal": int(summary.ordinal),
        "event_id": int(summary.eventId),
        "counts": {
            "measurements": int(summary.measurements),
            "space_points": int(summary.spacePoints),
            "particles": int(summary.particles),
            "selected_particles": int(summary.selectedParticles),
            "measurement_particles": int(summary.measurementParticles),
            "particle_measurements": int(summary.particleMeasurements),
        },
        "section_sha256": {
            "measurements": summary.measurementsSha256,
            "space_points": summary.spacePointsSha256,
            "particles": summary.particlesSha256,
            "selected_particles": summary.selectedParticlesSha256,
            "measurement_particles": summary.measurementParticlesSha256,
            "particle_measurements": summary.particleMeasurementsSha256,
        },
        "semantic_sha256": summary.semanticSha256,
    }


def main() -> int:
    args = parse_args()
    if args.protocol_id != PROVISIONAL_PROTOCOL_PREFIX and not args.protocol_id.startswith(
        PROVISIONAL_PROTOCOL_PREFIX + "-"
    ):
        raise ManifestError("protocol ID is outside the provisional namespace")
    if args.staging.exists():
        raise ManifestError("staging path already exists")
    if args.compression == "uncompressed" and args.compression_level != 0:
        raise ManifestError("uncompressed level must be zero")
    if args.compression != "uncompressed" and args.compression_level < 1:
        raise ManifestError("compressed payload level must be positive")
    if args.project_genesis_commit is not None and len(args.project_genesis_commit) != 40:
        raise ManifestError("project Genesis must be a full Git SHA or omitted")

    started = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    args.staging.mkdir(parents=True, exist_ok=False)
    payload_path = args.staging / "payload.root"

    build_identity = validate_private_build(
        args.private_source, args.private_build, args.identity_dir
    )
    geometry_identity = input_identities(args.geometry_dir)
    source_identity = source_file_identities()

    u = acts.UnitConstants
    detector = acts.examples.itk.buildITkGeometry(args.geometry_dir)
    tracking_geometry = detector.trackingGeometry()
    field = acts.root.MagneticFieldMapXyz(
        str(args.geometry_dir / "bfield/ATLAS-BField-xyz.root")
    )
    random_numbers = acts.examples.RandomNumbers(seed=42)
    sequencer = acts.examples.Sequencer(
        events=args.events,
        numThreads=1,
        outputDir=str(args.staging / "sequencer"),
    )
    addPythia8(
        sequencer,
        hardProcess=["Top:qqbar2ttbar=on"],
        npileup=200,
        vtxGen=acts.examples.GaussianVertexGenerator(
            stddev=acts.Vector4(
                0.0125 * u.mm,
                0.0125 * u.mm,
                55.5 * u.mm,
                5.0 * u.ns,
            ),
            mean=acts.Vector4(0, 0, 0, 0),
        ),
        rnd=random_numbers,
    )
    addGenParticleSelection(
        sequencer,
        ParticleSelectorConfig(
            rho=(0.0 * u.mm, 28.0 * u.mm),
            absZ=(0.0 * u.mm, 1.0 * u.m),
            eta=(-4.0, 4.0),
            pt=(150 * u.MeV, None),
        ),
    )
    addFatras(sequencer, tracking_geometry, field, rnd=random_numbers)
    addDigitization(
        sequencer,
        tracking_geometry,
        field,
        digiConfigFile=args.geometry_dir / "itk-hgtd/itk-smearing-config.json",
        rnd=random_numbers,
    )
    addDigiParticleSelection(
        sequencer,
        ParticleSelectorConfig(
            pt=(1.0 * u.GeV, None),
            eta=(-4.0, 4.0),
            measurements=(9, None),
            removeNeutral=True,
        ),
    )
    space_points = addSpacePointsMaking(
        sequencer,
        tracking_geometry,
        args.geometry_dir / "itk-hgtd/geoSelection-ITk.json",
        None,
        acts.logging.INFO,
    )

    writer_config = acts.examples.root.OwnedSeedingDatasetWriter.Config()
    writer_config.inputMeasurements = "measurements"
    writer_config.inputSpacePoints = space_points
    writer_config.inputParticles = "particles_simulated"
    writer_config.inputSelectedParticles = "particles_selected"
    writer_config.inputMeasurementParticlesMap = "measurement_particles_map"
    writer_config.inputParticleMeasurementsMap = "particle_measurements_map"
    writer_config.filePath = str(payload_path)
    writer_config.treeName = "events"
    writer_config.compression = args.compression
    writer_config.compressionLevel = args.compression_level
    writer = acts.examples.root.OwnedSeedingDatasetWriter(
        writer_config, acts.logging.INFO
    )
    sequencer.addWriter(writer)

    diagnostics, performance = add_exact_downstream(
        sequencer, tracking_geometry, field, log_level=acts.logging.INFO
    )
    sequencer.run()

    summaries = [event_summary(summary) for summary in writer.summaries()]
    if [summary["event_id"] for summary in summaries] != list(range(args.events)):
        raise ManifestError("writer did not complete every ordered event")
    diagnostic_output = diagnostics_dict(diagnostics.summaries())
    generated_raw = {
        "event_count": args.events,
        "completed_event_ids": list(range(args.events)),
        "input_event_hashes": [summary["semantic_sha256"] for summary in summaries],
        "stats": stats_dict(performance.stats()),
        "diagnostics": diagnostic_output,
    }
    atomic_write_json(args.staging / "generated-raw.json", generated_raw)

    finished = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    identities = {**build_identity, **geometry_identity, **source_identity}
    draft = {
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
        "protocol": {"id": args.protocol_id, "prefix": PROVISIONAL_PROTOCOL_PREFIX},
        "dataset": {
            "id": args.dataset_id,
            "event_count": args.events,
            "ordered_event_ids": list(range(args.events)),
            "events": summaries,
        },
        "payload_transport": {
            "file": "payload.root",
            "size_bytes": payload_path.stat().st_size,
            "sha256": sha256_file(payload_path),
            "root_uuid": writer.rootUuid(),
            "compression": {
                "algorithm": args.compression,
                "level": args.compression_level,
            },
        },
        "production_without_process_outcome": {
            "acts": {"tag": ACTS_TAG, "commit": ACTS_COMMIT},
            "project_genesis_commit": args.project_genesis_commit,
            "project_genesis_is_canonical": False,
            "seed": 42,
            "pileup": 200,
            "events": args.events,
            "threads": 1,
            "generator": "Pythia8",
            "hard_process": ["Top:qqbar2ttbar=on"],
            "host": socket.gethostname(),
            "container_image_sha256": args.container_image_sha256,
            "started_at": started,
            "finished_at": finished,
        },
        "identities": identities,
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
    atomic_write_json(args.staging / "production-draft.json", draft)
    print(f"staged_payload={payload_path}")
    print(f"payload_sha256={draft['payload_transport']['sha256']}")
    print(f"completed_events={args.events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
