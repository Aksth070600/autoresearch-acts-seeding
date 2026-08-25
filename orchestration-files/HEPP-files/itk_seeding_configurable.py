#!/usr/bin/env python3
"""Quick ITk CSV space-point seeding runner for ACTS v46.5.0."""

from __future__ import annotations

import argparse
import csv
import pathlib
import tempfile

import acts
import acts.examples
from acts.examples import CsvSpacePointReader, SeedsToProtoTracks
from acts.examples.itk import InputSpacePointsType
from acts.examples.reconstruction import addGridTripletSeeding


CSV_HEADER = (
    "measurement_id,sp_type,module_idhash,sp_x,sp_y,sp_z,sp_radius,sp_covr,sp_covz,"
    "sp_topHalfStripLength,sp_bottomHalfStripLength,sp_topStripDirection_0,"
    "sp_topStripDirection_1,sp_topStripDirection_2,sp_bottomStripDirection_0,"
    "sp_bottomStripDirection_1,sp_bottomStripDirection_2,sp_stripCenterDistance_0,"
    "sp_stripCenterDistance_1,sp_stripCenterDistance_2,sp_topStripCenterPosition_0,"
    "sp_topStripCenterPosition_1,sp_topStripCenterPosition_2"
)

# The upstream v46.5.0 example uses module hashes from an older geometry.  Zero
# is sufficient for this algorithm smoke test and avoids invalid source links.
PIXEL_ROWS = (
    (1, 0, 0, 30.0, 0.0, -50.0, 30.0, 0.06, 0.03),
    (2, 0, 0, 60.0, 8.0, -60.0, 60.530, 0.06, 0.03),
    (3, 0, 0, 90.0, 20.0, -70.0, 92.195, 0.06, 0.03),
    (4, 0, 0, 120.0, 38.0, -80.0, 125.858, 0.06, 0.03),
    (5, 0, 0, 150.0, 62.0, -90.0, 162.299, 0.06, 0.03),
    (6, 0, 0, 180.0, 92.0, -100.0, 202.119, 0.06, 0.03),
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ACTS GridTriplet seeding on ITk CSV space points."
    )
    parser.add_argument("--events", type=positive_int, default=1)
    parser.add_argument("--threads", type=positive_int, default=1)
    parser.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path.cwd() / "itk_seeding_output")
    parser.add_argument("--input-csv", type=pathlib.Path)
    parser.add_argument("--high-occupancy", action="store_true")
    return parser.parse_args()


def write_fixture(path: pathlib.Path) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(CSV_HEADER.split(","))
        for row in PIXEL_ROWS:
            writer.writerow((*row, *([0.0] * 14)))


def copy_input(path: pathlib.Path, destination: pathlib.Path) -> None:
    rows = list(csv.reader(path.read_text().splitlines()))
    if not rows:
        raise ValueError(f"input CSV is empty: {path}")
    header = [column.replace("[0]", "_0").replace("[1]", "_1").replace("[2]", "_2") for column in rows[0]]
    rows[0] = header
    with destination.open("w", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(rows)


def run(args: argparse.Namespace) -> None:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_type = InputSpacePointsType.PixelSpacePoints

    with tempfile.TemporaryDirectory(prefix="acts-itk-seeding-") as temporary:
        input_dir = pathlib.Path(temporary)
        input_path = input_dir / "event000000000-spacepoints_pixel.csv"
        if args.input_csv is None:
            write_fixture(input_path)
        else:
            copy_input(args.input_csv.resolve(), input_path)

        sequencer = acts.examples.Sequencer(
            events=args.events,
            numThreads=args.threads,
            logLevel=acts.logging.INFO,
        )
        reader = CsvSpacePointReader(
            level=acts.logging.INFO,
            inputStem="spacepoints",
            inputCollection="pixel",
            inputDir=str(input_dir),
            outputSpacePoints="PixelSpacePoint",
            extendCollection=True,
        )
        sequencer.addReader(reader)
        configs = acts.examples.itk.itkSeedingAlgConfig(
            input_type,
            highOccupancyConfig=args.high_occupancy,
        )
        seeds = addGridTripletSeeding(
            sequencer,
            reader.config.outputSpacePoints,
            *configs,
        )
        sequencer.addAlgorithm(
            SeedsToProtoTracks(
                level=acts.logging.INFO,
                inputSeeds=seeds,
                outputProtoTracks="seed-protoTracks",
            )
        )
        sequencer.run()


if __name__ == "__main__":
    run(parse_args())
