#!/usr/bin/env python3
"""Run the exact one-thread owned static-v4 qualification path."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

import acts
import acts.examples
import acts.examples.itk
import acts.examples.root

from candidate_identity import validate_candidate_build
from identity import input_identities, source_file_identities, validate_private_build
from pipeline import add_exact_downstream, diagnostics_dict, stats_dict
from schema import (
    ACTS_COMMIT,
    ACTS_TAG,
    ManifestError,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_dataset_directory,
)

MODULE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--geometry-dir", type=Path, required=True)
    parser.add_argument("--private-source", type=Path, required=True)
    parser.add_argument("--private-build", type=Path, required=True)
    parser.add_argument("--identity-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--raw-result", type=Path, required=True)
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--candidate-identity-dir", type=Path)
    parser.add_argument("--proposal-sha256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.output_dir.exists()
        or args.output_dir.is_symlink()
        or args.raw_result.exists()
        or args.raw_result.is_symlink()
    ):
        raise ManifestError("refusing to replace static output")

    # Byte and manifest identity validation occurs before geometry construction
    # or any seeding algorithm is configured.
    manifest, detached = validate_dataset_directory(
        args.dataset,
        expected_protocol_id=args.protocol_id,
        expected_dataset_id=args.dataset_id,
    )
    if (args.candidate_identity_dir is None) != (args.proposal_sha256 is None):
        raise ManifestError(
            "candidate identity directory and proposal hash must be supplied together"
        )
    if args.candidate_identity_dir is None:
        build_identity = validate_private_build(
            args.private_source, args.private_build, args.identity_dir
        )
        if any(
            manifest["identities"][key] != value
            for key, value in build_identity.items()
        ):
            raise ManifestError("static Genesis source/build differs from dataset production")
        candidate_binding = None
    else:
        if len(args.proposal_sha256) != 64:
            raise ManifestError("candidate proposal hash is malformed")
        build_identity, _ = validate_candidate_build(
            args.private_source,
            args.private_build,
            args.candidate_identity_dir,
            args.proposal_sha256,
        )
        if (
            manifest["identities"]["overlay_manifest_sha256"]
            != build_identity["overlay_manifest_sha256"]
        ):
            raise ManifestError("candidate overlay differs from dataset production")
        candidate_binding = dict(build_identity)
    geometry_identity = input_identities(args.geometry_dir)
    if any(
        manifest["identities"][key] != value
        for key, value in geometry_identity.items()
    ):
        raise ManifestError("static geometry/field/config identity mismatch")
    source_identity = source_file_identities()
    for key in ("writer_source_sha256", "reader_source_sha256"):
        if manifest["identities"][key] != source_identity[key]:
            raise ManifestError("owned C++ source identity mismatch")
    if tuple(acts.__version__) != (46, 5, 0):
        raise ManifestError("loaded ACTS Python version mismatch")

    output_parent = args.output_dir.parent.resolve(strict=True)
    staging_output = Path(
        tempfile.mkdtemp(prefix=f".{args.output_dir.name}.run-", dir=output_parent)
    )
    published_output = False
    try:
        raw = _run_static(
            args,
            manifest,
            detached,
            build_identity,
            candidate_binding,
            staging_output,
        )
        os.replace(staging_output, args.output_dir)
        published_output = True
        atomic_write_json(args.raw_result, raw)
    except BaseException:
        shutil.rmtree(staging_output, ignore_errors=True)
        if published_output:
            shutil.rmtree(args.output_dir, ignore_errors=True)
        if args.raw_result.exists() and not args.raw_result.is_symlink():
            args.raw_result.unlink()
        raise
    print(f"static_completed_events={manifest['dataset']['event_count']}")
    print(f"static_raw_result={args.raw_result}")
    return 0


def _run_static(
    args, manifest, detached, build_identity, candidate_binding, staging_output: Path
) -> dict:
    detector = acts.examples.itk.buildITkGeometry(args.geometry_dir)
    tracking_geometry = detector.trackingGeometry()
    field = acts.root.MagneticFieldMapXyz(
        str(args.geometry_dir / "bfield/ATLAS-BField-xyz.root")
    )
    events = manifest["dataset"]["event_count"]
    sequencer = acts.examples.Sequencer(
        events=events,
        numThreads=1,
        outputDir=str(staging_output),
    )
    reader_config = acts.examples.root.OwnedSeedingDatasetReader.Config()
    reader_config.filePath = str(args.dataset / "payload.root")
    reader_config.treeName = "events"
    reader_config.outputMeasurements = "measurements"
    reader_config.outputMeasurementSubset = "measurement_subset"
    reader_config.outputSpacePoints = "spacepoints"
    reader_config.outputParticles = "particles_simulated"
    reader_config.outputSelectedParticles = "particles_selected"
    reader_config.outputMeasurementParticlesMap = "measurement_particles_map"
    reader_config.outputParticleMeasurementsMap = "particle_measurements_map"
    reader_config.expectedEventIds = manifest["dataset"]["ordered_event_ids"]
    reader_config.expectedEventHashes = [
        event["semantic_sha256"] for event in manifest["dataset"]["events"]
    ]
    reader_config.trackingGeometry = tracking_geometry
    reader = acts.examples.root.OwnedSeedingDatasetReader(
        reader_config, acts.logging.INFO
    )
    sequencer.addReader(reader)
    diagnostics, performance = add_exact_downstream(
        sequencer, tracking_geometry, field, log_level=acts.logging.INFO
    )
    sequencer.run()

    completed_ids = [int(value) for value in reader.completedEventIds()]
    completed_hashes = list(reader.completedEventHashes())
    diagnostic_output = diagnostics_dict(diagnostics.summaries())
    raw_diagnostics = {
        key: diagnostic_output[key]
        for key in (
            "raw_seed_count",
            "estimated_seed_count",
            "estimated_parameter_count",
            "converted_track_count",
            "matcher_classification_counts",
            "ordered_diagnostics_sha256",
        )
    }
    loaded_dsos = _loaded_private_dsos(args.private_build)
    loaded_dso_manifest_sha256 = sha256_bytes(canonical_json_bytes(loaded_dsos))
    raw = {
        "protocol_id": manifest["protocol"]["id"],
        "dataset_id": manifest["dataset"]["id"],
        "event_count": events,
        "thread_count": 1,
        "completed_event_ids": completed_ids,
        "input_event_hashes": completed_hashes,
        "stats": stats_dict(performance.stats()),
        "diagnostics": raw_diagnostics,
        "identities": {
            "acts_tag": ACTS_TAG,
            "acts_commit": ACTS_COMMIT,
            "manifest_sha256": detached["manifest.json"],
            "payload_sha256": detached["payload.root"],
            "dataset_source_manifest_sha256": manifest["identities"]["source_manifest_sha256"],
            "dataset_build_manifest_sha256": manifest["identities"]["build_manifest_sha256"],
            "runtime_source_manifest_sha256": build_identity["source_manifest_sha256"],
            "runtime_build_manifest_sha256": build_identity["build_manifest_sha256"],
            "overlay_manifest_sha256": build_identity["overlay_manifest_sha256"],
            "loaded_dso_manifest_sha256": loaded_dso_manifest_sha256,
            "runner_sha256": sha256_file(MODULE / "run_static.py"),
        },
        "candidate_binding": candidate_binding,
        "loaded_dsos": loaded_dsos,
        "expected_unmasked_fpes": 0,
        "root_plots": False,
    }
    atomic_write_json(staging_output / "diagnostics.json", diagnostic_output)
    return raw


def _loaded_private_dsos(build: Path) -> dict[str, str]:
    build = build.resolve(strict=True)
    shared_build = Path("/storage/thomaaks/acts-v46.5.0/build")
    paths: set[Path] = set()
    for line in Path("/proc/self/maps").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 6 or not fields[-1].startswith("/"):
            continue
        path = Path(fields[-1]).resolve(strict=False)
        if shared_build == path or shared_build in path.parents:
            raise ManifestError(f"shared Genesis DSO was loaded: {path}")
        if build == path or build in path.parents:
            paths.add(path)
    if not paths or not any(path.name == "libActsCore.so" for path in paths):
        raise ManifestError("loaded private ACTS DSO closure is missing ActsCore")
    return {
        path.relative_to(build).as_posix(): sha256_file(path)
        for path in sorted(paths)
        if path.is_file()
    }


if __name__ == "__main__":
    raise SystemExit(main())
