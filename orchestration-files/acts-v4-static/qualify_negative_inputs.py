#!/usr/bin/env python3
"""Run destructive one-event input checks in isolated qualification copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from schema import ManifestError, canonical_json_bytes, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--geometry-dir", type=Path, required=True)
    parser.add_argument("--private-source", type=Path, required=True)
    parser.add_argument("--private-build", type=Path, required=True)
    parser.add_argument("--identity-dir", type=Path, required=True)
    parser.add_argument("--protocol-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    return parser.parse_args()


def write_manifest(dataset: Path, manifest: dict) -> None:
    manifest_bytes = canonical_json_bytes(manifest)
    (dataset / "manifest.json").write_bytes(manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    payload_hash = sha256_file(dataset / "payload.root")
    (dataset / "SHA256SUMS").write_text(
        f"{manifest_hash}  manifest.json\n{payload_hash}  payload.root\n",
        encoding="ascii",
    )


def bind_mutated_payload(dataset: Path) -> None:
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    payload = dataset / "payload.root"
    manifest["payload"]["sha256"] = sha256_file(payload)
    manifest["payload"]["size_bytes"] = payload.stat().st_size
    write_manifest(dataset, manifest)


def rewrite_root(payload: Path, mutate: Callable[[object], None]) -> None:
    import ROOT

    temporary = payload.with_name("mutated.root")
    source = ROOT.TFile.Open(str(payload), "READ")
    if source is None or source.IsZombie():
        raise ManifestError("could not open source ROOT payload")
    tree = source.Get("events")
    if tree is None or tree.GetEntries() != 1:
        raise ManifestError("negative qualification requires one ROOT event")
    output = ROOT.TFile.Open(str(temporary), "RECREATE")
    clone = tree.CloneTree(0)
    tree.GetEntry(0)
    mutate(tree)
    clone.Fill()
    clone.Write()
    output.Close()
    source.Close()
    os.replace(temporary, payload)


def run_rejected(args: argparse.Namespace, name: str, dataset: Path, expected: str) -> None:
    case = args.workspace / name
    case.mkdir()
    output = case / "output"
    raw = case / "raw.json"
    environment = dict(os.environ)
    environment["ACTS_SEQUENCER_FAIL_ON_UNMASKED_FPE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "run_static.py"),
            "--dataset",
            str(dataset),
            "--geometry-dir",
            str(args.geometry_dir),
            "--private-source",
            str(args.private_source),
            "--private-build",
            str(args.private_build),
            "--identity-dir",
            str(args.identity_dir),
            "--output-dir",
            str(output),
            "--raw-result",
            str(raw),
            "--protocol-id",
            args.protocol_id,
            "--dataset-id",
            args.dataset_id,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=environment,
    )
    (case / "rejection.log").write_text(process.stdout, encoding="utf-8")
    if process.returncode == 0 or expected not in process.stdout:
        raise ManifestError(
            f"negative case {name} did not reject with {expected!r}: rc={process.returncode}"
        )
    if output.exists() or output.is_symlink() or raw.exists() or raw.is_symlink():
        raise ManifestError(f"negative case {name} published partial output")
    hidden = list(case.glob(f".{output.name}.run-*"))
    if hidden:
        raise ManifestError(f"negative case {name} retained hidden partial output")
    print(f"negative_case={name} rejected=ok partial_output=none")


def copied_case(args: argparse.Namespace, name: str) -> Path:
    destination = args.workspace / f"{name}-dataset"
    shutil.copytree(args.dataset, destination)
    return destination


def main() -> int:
    args = parse_args()
    if args.workspace.exists() or args.workspace.is_symlink():
        raise ManifestError("negative qualification workspace already exists")
    args.workspace.mkdir(parents=True)

    dataset = copied_case(args, "payload-byte-tamper")
    payload = dataset / "payload.root"
    with payload.open("r+b") as stream:
        stream.seek(-1, os.SEEK_END)
        byte = stream.read(1)
        stream.seek(-1, os.SEEK_END)
        stream.write(bytes([byte[0] ^ 1]))
    run_rejected(
        args, "payload-byte-tamper", dataset, "detached hash mismatch for payload.root"
    )

    dataset = copied_case(args, "manifest-hash-tamper")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    manifest["dataset"]["id"] += "-tampered"
    (dataset / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    run_rejected(
        args,
        "manifest-hash-tamper",
        dataset,
        "detached hash mismatch for manifest.json",
    )

    dataset = copied_case(args, "protocol-drift")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    manifest["protocol"]["id"] = "acts-seeding-v3"
    write_manifest(dataset, manifest)
    run_rejected(args, "protocol-drift", dataset, "protocol.id is outside")

    root_cases: tuple[tuple[str, Callable[[object], None], str], ...] = (
        (
            "malformed-csr",
            lambda tree: tree.measurement_value_offset.__setitem__(0, 1),
            "measurement CSR offsets must start at zero",
        ),
        (
            "non-finite",
            lambda tree: tree.spacepoint_x.__setitem__(0, float("nan")),
            "non-finite space-point x",
        ),
        (
            "unresolved-geometry",
            lambda tree: tree.measurement_geometry_id.__setitem__(0, 1),
            "unresolved measurement geometry ID",
        ),
        (
            "unresolved-source",
            lambda tree: tree.spacepoint_source_measurement_index.__setitem__(
                0, int(tree.measurement_count) + 1
            ),
            "space-point source measurement is unresolved",
        ),
        (
            "unresolved-truth",
            lambda tree: tree.measurement_particles_barcode.__setitem__(
                2, 2**32 - 1
            ),
            "unresolved forward relation particle",
        ),
        (
            "barcode-integer-range",
            lambda tree: tree.particle_barcode.__setitem__(0, 2**16),
            "barcode component exceeds its integer range",
        ),
        (
            "generation-process-enum",
            lambda tree: tree.particle_process.__setitem__(0, 5),
            "particle generation process is out of range",
        ),
        (
            "simulation-outcome-enum",
            lambda tree: tree.particle_final_outcome.__setitem__(0, 5),
            "particle simulation outcome is out of range",
        ),
        (
            "map-inversion",
            lambda tree: tree.particle_measurements_measurement_index.__setitem__(
                0,
                (int(tree.particle_measurements_measurement_index[0]) + 1)
                % int(tree.measurement_count),
            ),
            "truth maps are not exact inverse multisets",
        ),
    )
    for name, mutation, expected in root_cases:
        dataset = copied_case(args, name)
        rewrite_root(dataset / "payload.root", mutation)
        bind_mutated_payload(dataset)
        run_rejected(args, name, dataset, expected)

    print(f"negative_qualification=passed cases={3 + len(root_cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
