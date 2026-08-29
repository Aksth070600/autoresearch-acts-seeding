#!/usr/bin/env python3
"""Shared exact downstream static-v4 seeding and diagnostics pipeline."""

from __future__ import annotations

import acts
import acts.examples
import acts.examples.itk
import acts.examples.root
from acts.examples.reconstruction import addGridTripletSeeding

from schema import canonical_json_bytes, sha256_bytes


def add_exact_downstream(
    sequencer,
    tracking_geometry,
    field,
    *,
    space_points: str = "spacepoints",
    measurements: str = "measurement_subset",
    selected_particles: str = "particles_selected",
    measurement_particles: str = "measurement_particles_map",
    particle_measurements: str = "particle_measurements_map",
    prefix: str = "",
    log_level=acts.logging.INFO,
):
    """Add the report-selected GridTriplet through exact collector path."""
    u = acts.UnitConstants
    config = acts.examples.itk.itkSeedingAlgConfig(
        acts.examples.itk.InputSpacePointsType.PixelSpacePoints
    )
    raw_seeds = addGridTripletSeeding(
        sequencer,
        space_points,
        *config,
        logLevel=log_level,
        outputSeeds=f"{prefix}seeds",
    )
    estimated_seeds = f"{prefix}estimatedseeds"
    estimated_parameters = f"{prefix}estimatedparameters"
    sequencer.addAlgorithm(
        acts.examples.TrackParamsEstimationAlgorithm(
            level=log_level,
            inputSeeds=raw_seeds,
            outputTrackParameters=estimated_parameters,
            outputSeeds=estimated_seeds,
            trackingGeometry=tracking_geometry,
            magneticField=field,
            initialSigmas=[
                1 * u.mm,
                1 * u.mm,
                1 * u.degree,
                1 * u.degree,
                0 * u.e / u.GeV,
                1 * u.ns,
            ],
            initialSigmaQoverPt=0.1 * u.e / u.GeV,
            initialSigmaPtRel=0.1,
            initialVarInflation=[1.0] * 6,
        )
    )
    proto_tracks = f"{prefix}seed-protoTracks"
    sequencer.addAlgorithm(
        acts.examples.SeedsToProtoTracks(
            level=log_level,
            inputSeeds=estimated_seeds,
            outputProtoTracks=proto_tracks,
        )
    )
    tracks = f"{prefix}seed-tracks"
    sequencer.addAlgorithm(
        acts.examples.ProtoTracksToTracks(
            level=log_level,
            inputProtoTracks=proto_tracks,
            inputTrackParameters=estimated_parameters,
            inputMeasurements=measurements,
            outputTracks=tracks,
        )
    )
    track_particle_matching = f"{prefix}seed_particle_matching"
    particle_track_matching = f"{prefix}particle_seed_matching"
    sequencer.addAlgorithm(
        acts.examples.TrackTruthMatcher(
            level=log_level,
            inputTracks=tracks,
            inputParticles=selected_particles,
            inputMeasurementParticlesMap=measurement_particles,
            outputTrackParticleMatching=track_particle_matching,
            outputParticleTrackMatching=particle_track_matching,
            matchingRatio=1.0,
            doubleMatching=False,
        )
    )

    diagnostic_config = acts.examples.root.OwnedSeedingDiagnosticsWriter.Config()
    diagnostic_config.inputRawSeeds = raw_seeds
    diagnostic_config.inputEstimatedSeeds = estimated_seeds
    diagnostic_config.inputEstimatedParameters = estimated_parameters
    diagnostic_config.inputTracks = tracks
    diagnostic_config.inputTrackParticleMatching = track_particle_matching
    diagnostic_config.inputParticleTrackMatching = particle_track_matching
    diagnostics = acts.examples.root.OwnedSeedingDiagnosticsWriter(
        diagnostic_config, log_level
    )
    sequencer.addWriter(diagnostics)

    performance_config = acts.examples.PythonTrackFinderPerformanceWriter.Config()
    performance_config.inputTracks = tracks
    performance_config.inputParticles = selected_particles
    performance_config.inputTrackParticleMatching = track_particle_matching
    performance_config.inputParticleTrackMatching = particle_track_matching
    performance_config.inputParticleMeasurementsMap = particle_measurements
    performance_config.effPlotToolConfig = acts.examples.root.EffPlotToolConfig()
    performance_config.fakePlotToolConfig = acts.examples.root.FakePlotToolConfig()
    performance_config.duplicationPlotToolConfig = (
        acts.examples.root.DuplicationPlotToolConfig()
    )
    performance_config.trackSummaryPlotToolConfig = (
        acts.examples.root.TrackSummaryPlotToolConfig()
    )
    performance_config.trackQualityPlotToolConfig = (
        acts.examples.root.TrackQualityPlotToolConfig()
    )
    performance = acts.examples.PythonTrackFinderPerformanceWriter(
        performance_config, log_level
    )
    sequencer.addWriter(performance)
    return diagnostics, performance


def stats_dict(stats) -> dict[str, int]:
    names = (
        "nTotalTracks",
        "nTotalMatchedTracks",
        "nTotalFakeTracks",
        "nTotalDuplicateTracks",
        "nTotalParticles",
        "nTotalMatchedParticles",
        "nTotalDuplicateParticles",
        "nTotalFakeParticles",
    )
    return {name: int(getattr(stats, name)) for name in names}


def diagnostics_dict(summaries) -> dict:
    values = list(summaries)
    events = [
            {
                "event_id": int(summary.eventId),
                "raw_seed_count": int(summary.rawSeeds),
                "estimated_seed_count": int(summary.estimatedSeeds),
                "estimated_parameter_count": int(summary.estimatedParameters),
                "converted_track_count": int(summary.convertedTracks),
                "matcher_classification_counts": {
                    "matched": int(summary.matchedTracks),
                    "fake": int(summary.fakeTracks),
                    "duplicate": int(summary.duplicateTracks),
                    "unknown": int(summary.unknownTracks),
                },
                "semantic_sha256": summary.semanticSha256,
            }
            for summary in values
        ]
    return {
        "events": events,
        "ordered_diagnostics_sha256": sha256_bytes(canonical_json_bytes(events)),
        "raw_seed_count": sum(int(summary.rawSeeds) for summary in values),
        "estimated_seed_count": sum(int(summary.estimatedSeeds) for summary in values),
        "estimated_parameter_count": sum(
            int(summary.estimatedParameters) for summary in values
        ),
        "converted_track_count": sum(int(summary.convertedTracks) for summary in values),
        "matcher_classification_counts": {
            key: sum(
                int(
                    getattr(
                        summary,
                        {
                            "matched": "matchedTracks",
                            "fake": "fakeTracks",
                            "duplicate": "duplicateTracks",
                            "unknown": "unknownTracks",
                        }[key],
                    )
                )
                for summary in values
            )
            for key in ("matched", "fake", "duplicate", "unknown")
        },
    }
