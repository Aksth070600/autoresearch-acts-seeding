#!/usr/bin/env python3
"""Configurable development runner derived from ACTS v46.5.0 full_chain_itk.py."""

from __future__ import annotations

import argparse
import pathlib

import acts
import acts.examples
import acts.examples.itk
import acts.root
from acts.examples.reconstruction import (
    AmbiguityResolutionConfig,
    CkfConfig,
    SeedingAlgorithm,
    TrackSelectorConfig,
    VertexFinder,
    addAmbiguityResolution,
    addCKFTracks,
    addSeeding,
    addVertexFitting,
)
from acts.examples.simulation import (
    ParticleSelectorConfig,
    addDigiParticleSelection,
    addDigitization,
    addFatras,
    addGenParticleSelection,
    addPythia8,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the configurable ACTS ITk full-chain development workload."
    )
    parser.add_argument("--events", type=positive_int, default=10)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path.cwd() / "itk_output")
    parser.add_argument("--workload", choices=("ttbar_pu200",), default="ttbar_pu200")
    parser.add_argument("--stage", choices=("seeding", "full"), default="full")
    parser.add_argument("--pileup", type=positive_int, default=200)
    parser.add_argument("--geometry-dir", type=pathlib.Path, default=pathlib.Path("acts-itk"))
    return parser.parse_args()


def run(args: argparse.Namespace) -> None:
    u = acts.UnitConstants
    geo_dir = args.geometry_dir
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    detector = acts.examples.itk.buildITkGeometry(geo_dir)
    tracking_geometry = detector.trackingGeometry()
    field = acts.root.MagneticFieldMapXyz(str(geo_dir / "bfield/ATLAS-BField-xyz.root"))
    rnd = acts.examples.RandomNumbers(seed=args.seed)

    sequencer = acts.examples.Sequencer(
        events=args.events,
        numThreads=args.threads,
        outputDir=str(output_dir),
    )

    addPythia8(
        sequencer,
        hardProcess=["Top:qqbar2ttbar=on"],
        npileup=args.pileup,
        vtxGen=acts.examples.GaussianVertexGenerator(
            stddev=acts.Vector4(
                0.0125 * u.mm,
                0.0125 * u.mm,
                55.5 * u.mm,
                5.0 * u.ns,
            ),
            mean=acts.Vector4(0, 0, 0, 0),
        ),
        rnd=rnd,
        outputDirRoot=output_dir,
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

    addFatras(
        sequencer,
        tracking_geometry,
        field,
        rnd=rnd,
        outputDirRoot=output_dir,
    )
    addDigitization(
        sequencer,
        tracking_geometry,
        field,
        digiConfigFile=geo_dir / "itk-hgtd/itk-smearing-config.json",
        outputDirRoot=output_dir,
        rnd=rnd,
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
    addSeeding(
        sequencer,
        tracking_geometry,
        field,
        seedingAlgorithm=SeedingAlgorithm.GridTriplet,
        *acts.examples.itk.itkSeedingAlgConfig(
            acts.examples.itk.InputSpacePointsType.PixelSpacePoints
        ),
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
        geoSelectionConfigFile=geo_dir / "itk-hgtd/geoSelection-ITk.json",
        outputDirRoot=output_dir,
    )
    if args.stage == "seeding":
        sequencer.run()
        return

    addCKFTracks(
        sequencer,
        tracking_geometry,
        field,
        trackSelectorConfig=(
            TrackSelectorConfig(absEta=(None, 2.0), pt=(0.9 * u.GeV, None), nMeasurementsMin=9, maxHoles=2, maxOutliers=2, maxSharedHits=2),
            TrackSelectorConfig(absEta=(None, 2.6), pt=(0.4 * u.GeV, None), nMeasurementsMin=8, maxHoles=2, maxOutliers=2, maxSharedHits=2),
            TrackSelectorConfig(absEta=(None, 4.0), pt=(0.4 * u.GeV, None), nMeasurementsMin=7, maxHoles=2, maxOutliers=2, maxSharedHits=2),
        ),
        ckfConfig=CkfConfig(
            seedDeduplication=True,
            stayOnSeed=True,
            pixelVolumes=[8, 9, 10, 13, 14, 15, 16, 18, 19, 20],
            stripVolumes=[22, 23, 24],
            maxPixelHoles=1,
            maxStripHoles=2,
        ),
        outputDirRoot=output_dir,
    )
    addAmbiguityResolution(
        sequencer,
        AmbiguityResolutionConfig(
            maximumSharedHits=3,
            maximumIterations=10000,
            nMeasurementsMin=6,
        ),
        outputDirRoot=output_dir,
    )
    addVertexFitting(
        sequencer,
        field,
        vertexFinder=VertexFinder.AMVF,
        outputDirRoot=output_dir,
    )
    sequencer.run()


if __name__ == "__main__":
    run(parse_args())
