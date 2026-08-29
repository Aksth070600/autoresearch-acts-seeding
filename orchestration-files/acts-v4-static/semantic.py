#!/usr/bin/env python3
"""Canonical semantic stream for the owned static v1 payload.

This Python implementation qualifies fixtures and independently specifies the
byte stream implemented by the C++ reader/writer. ROOT transport bytes and key
metadata are deliberately outside this stream.
"""

from __future__ import annotations

import hashlib
import math
import struct
import sys
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

from schema import CANONICAL_STREAM_ID, EVENT_SECTIONS, ManifestError

_STATE_KEYS = (
    "position4",
    "direction3",
    "absolute_momentum",
    "proper_time",
    "path_in_x0",
    "path_in_l0",
    "number_of_hits",
    "outcome",
)


class CanonicalStream:
    def __init__(self) -> None:
        self._data = bytearray()

    def u8(self, value: int) -> None:
        self._data += struct.pack("<B", value)

    def u32(self, value: int) -> None:
        self._data += struct.pack("<I", value)

    def i32(self, value: int) -> None:
        self._data += struct.pack("<i", value)

    def u64(self, value: int) -> None:
        self._data += struct.pack("<Q", value)

    def f32(self, value: float) -> None:
        self._data += struct.pack("<f", value)

    def f64(self, value: float) -> None:
        self._data += struct.pack("<d", value)

    def text(self, value: str) -> None:
        encoded = value.encode("ascii")
        self.u64(len(encoded))
        self._data += encoded

    def digest(self) -> bytes:
        return hashlib.sha256(self._data).digest()

    def hexdigest(self) -> str:
        return hashlib.sha256(self._data).hexdigest()


def _keys(value: Any, path: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ManifestError(f"{path} has an invalid object shape")
    return value


def _array(value: Any, path: str, length: int | None = None) -> list[Any]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        suffix = "" if length is None else f" with length {length}"
        raise ManifestError(f"{path} must be an array{suffix}")
    return value


def _int(value: Any, path: str, *, minimum: int = 0, maximum: int = 2**64 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ManifestError(f"{path} is outside [{minimum}, {maximum}]")
    return value


def _float(value: Any, path: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ManifestError(f"{path} must be finite{' and nonnegative' if nonnegative else ''}")
    return result


def _barcode(value: Any, path: str) -> tuple[int, int, int, int, int]:
    parts = _array(value, path, 5)
    limits = (2**16 - 1, 2**16 - 1, 2**32 - 1, 2**8 - 1, 2**32 - 1)
    result = tuple(_int(part, f"{path}[{index}]", maximum=limits[index]) for index, part in enumerate(parts))
    if result == (0, 0, 0, 0, 0):
        raise ManifestError(f"{path} is an invalid zero barcode")
    return result  # type: ignore[return-value]


def _write_barcode(stream: CanonicalStream, barcode: Sequence[int]) -> None:
    for part in barcode:
        stream.u32(part)


def _write_state(stream: CanonicalStream, state: Mapping[str, Any], path: str) -> None:
    _keys(state, path, set(_STATE_KEYS))
    for index, value in enumerate(_array(state["position4"], f"{path}.position4", 4)):
        stream.f64(_float(value, f"{path}.position4[{index}]"))
    direction = [_float(value, f"{path}.direction3[{index}]") for index, value in enumerate(_array(state["direction3"], f"{path}.direction3", 3))]
    squared_norm = sum(value * value for value in direction)
    unit_tolerance = 64 * sys.float_info.epsilon
    if not math.isfinite(squared_norm) or abs(squared_norm - 1.0) > unit_tolerance:
        raise ManifestError(f"{path}.direction3 must have unit length")
    for value in direction:
        stream.f64(value)
    stream.f64(_float(state["absolute_momentum"], f"{path}.absolute_momentum", nonnegative=True))
    stream.f64(_float(state["proper_time"], f"{path}.proper_time"))
    stream.f64(_float(state["path_in_x0"], f"{path}.path_in_x0", nonnegative=True))
    stream.f64(_float(state["path_in_l0"], f"{path}.path_in_l0", nonnegative=True))
    stream.u32(_int(state["number_of_hits"], f"{path}.number_of_hits", maximum=2**32 - 1))
    stream.u32(_int(state["outcome"], f"{path}.outcome", maximum=4))


def validate_and_hash_event(
    event: Any,
    *,
    expected_ordinal: int | None = None,
    expected_event_id: int | None = None,
    resolvable_geometry_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Validate one JSON-shaped event and return counts and semantic hashes."""
    value = _keys(
        event,
        "event",
        {
            "ordinal",
            "event_id",
            "measurements",
            "space_points",
            "particles",
            "measurement_particles",
            "particle_measurements",
        },
    )
    ordinal = _int(value["ordinal"], "event.ordinal", maximum=2**32 - 1)
    event_id = _int(value["event_id"], "event.event_id")
    if expected_ordinal is not None and ordinal != expected_ordinal:
        raise ManifestError("event ordinal mismatch")
    if expected_event_id is not None and event_id != expected_event_id:
        raise ManifestError("event ID mismatch")

    section_hashes: dict[str, str] = {}
    counts: dict[str, int] = {}

    measurements = _array(value["measurements"], "event.measurements")
    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("measurements")
    stream.u64(len(measurements))
    measurement_geometry: list[int] = []
    for index, raw in enumerate(measurements):
        row = _keys(
            raw,
            f"measurement[{index}]",
            {"index", "geometry_id", "subspace_indices", "parameters", "covariance"},
        )
        if row["index"] != index:
            raise ManifestError("measurement indices are not contiguous and ordered")
        geometry_id = _int(row["geometry_id"], f"measurement[{index}].geometry_id")
        if geometry_id == 0:
            raise ManifestError("measurement geometry ID is zero")
        if resolvable_geometry_ids is not None and geometry_id not in resolvable_geometry_ids:
            raise ManifestError("measurement geometry ID is unresolved")
        measurement_geometry.append(geometry_id)
        subspace = _array(row["subspace_indices"], f"measurement[{index}].subspace_indices")
        size = len(subspace)
        if not 1 <= size <= 6:
            raise ManifestError("measurement size is outside 1..6")
        indices = [_int(item, f"measurement[{index}].subspace_indices", maximum=5) for item in subspace]
        if indices != sorted(set(indices)):
            raise ManifestError("measurement subspace indices are not ordered and unique")
        parameters = _array(row["parameters"], f"measurement[{index}].parameters", size)
        covariance = _array(row["covariance"], f"measurement[{index}].covariance", size * size)
        stream.u64(index)
        stream.u64(geometry_id)
        stream.u8(size)
        stream.u64(size)
        for item in indices:
            stream.u8(item)
        stream.u64(size)
        for item in parameters:
            stream.f64(_float(item, f"measurement[{index}].parameters"))
        stream.u64(size * size)
        for item in covariance:
            stream.f64(_float(item, f"measurement[{index}].covariance"))
    counts["measurements"] = len(measurements)
    section_hashes["measurements"] = stream.hexdigest()

    space_points = _array(value["space_points"], "event.space_points")
    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("space_points")
    stream.u64(len(space_points))
    for index, raw in enumerate(space_points):
        row = _keys(
            raw,
            f"space_point[{index}]",
            {
                "index",
                "kind",
                "overlap_class",
                "x",
                "y",
                "z",
                "r",
                "time_valid",
                "time",
                "variance_r",
                "variance_z",
                "source_links",
            },
        )
        if row["index"] != index or row["kind"] != 0 or row["overlap_class"] != 0:
            raise ManifestError("space-point index/kind/overlap contract mismatch")
        if type(row["time_valid"]) is not bool:
            raise ManifestError("space-point time_valid must be a boolean")
        time = _float(row["time"], f"space_point[{index}].time")
        if not row["time_valid"] and struct.pack("<f", time) != struct.pack("<f", 0.0):
            raise ManifestError("space point without time must store canonical +0")
        sources = _array(row["source_links"], f"space_point[{index}].source_links", 1)
        source = _keys(sources[0], "source link", {"geometry_id", "measurement_index"})
        measurement_index = _int(source["measurement_index"], "source measurement index")
        if measurement_index >= len(measurements):
            raise ManifestError("space-point source link is out of range")
        source_geometry = _int(source["geometry_id"], "source geometry ID")
        if source_geometry != measurement_geometry[measurement_index]:
            raise ManifestError("source-link and measurement geometry IDs differ")
        if resolvable_geometry_ids is not None and source_geometry not in resolvable_geometry_ids:
            raise ManifestError("source-link geometry ID is unresolved")
        stream.u32(index)
        stream.u8(0)
        stream.u8(0)
        for key in ("x", "y", "z", "r"):
            stream.f32(_float(row[key], f"space_point[{index}].{key}"))
        stream.u8(int(row["time_valid"]))
        stream.f32(time)
        stream.f32(_float(row["variance_r"], "variance_r", nonnegative=True))
        stream.f32(_float(row["variance_z"], "variance_z", nonnegative=True))
        stream.u64(1)
        stream.u64(source_geometry)
        stream.u64(measurement_index)
    counts["space_points"] = len(space_points)
    section_hashes["space_points"] = stream.hexdigest()

    particles = _array(value["particles"], "event.particles")
    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("particles")
    stream.u64(len(particles))
    particle_ids: list[tuple[int, int, int, int, int]] = []
    selected_ids: list[tuple[int, int, int, int, int]] = []
    for index, raw in enumerate(particles):
        row = _keys(
            raw,
            f"particle[{index}]",
            {"barcode", "pdg", "process", "charge", "mass", "initial", "final", "selected"},
        )
        barcode = _barcode(row["barcode"], f"particle[{index}].barcode")
        if particle_ids and barcode <= particle_ids[-1]:
            raise ManifestError("particle barcodes are duplicated or not ordered")
        particle_ids.append(barcode)
        if type(row["selected"]) is not bool:
            raise ManifestError("particle selected marker must be a boolean")
        if row["selected"]:
            selected_ids.append(barcode)
        _write_barcode(stream, barcode)
        pdg = _int(row["pdg"], "particle.pdg", minimum=-(2**31), maximum=2**31 - 1)
        if pdg == 0:
            raise ManifestError("particle.pdg must not be the invalid zero code")
        stream.i32(pdg)
        stream.u32(_int(row["process"], "particle.process", maximum=4))
        stream.f64(_float(row["charge"], "particle.charge"))
        stream.f64(_float(row["mass"], "particle.mass", nonnegative=True))
        _write_state(stream, row["initial"], "particle.initial")
        _write_state(stream, row["final"], "particle.final")
        stream.u8(int(row["selected"]))
    particle_set = set(particle_ids)
    counts["particles"] = len(particles)
    section_hashes["particles"] = stream.hexdigest()

    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("selected_particles")
    stream.u64(len(selected_ids))
    for barcode in selected_ids:
        _write_barcode(stream, barcode)
    counts["selected_particles"] = len(selected_ids)
    section_hashes["selected_particles"] = stream.hexdigest()

    forward_pairs: list[tuple[int, tuple[int, int, int, int, int]]] = []
    forward = _array(value["measurement_particles"], "event.measurement_particles")
    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("measurement_particles")
    stream.u64(len(forward))
    for ordinal_index, raw in enumerate(forward):
        row = _keys(raw, "measurement_particles row", {"ordinal", "measurement_index", "barcode"})
        if row["ordinal"] != ordinal_index:
            raise ManifestError("measurement-particle relation ordinals are malformed")
        measurement_index = _int(row["measurement_index"], "measurement relation index")
        if measurement_index >= len(measurements):
            raise ManifestError("measurement-particle relation has an unresolved measurement")
        barcode = _barcode(row["barcode"], "measurement relation barcode")
        if barcode not in particle_set:
            raise ManifestError("measurement-particle relation has an unresolved particle")
        pair = (measurement_index, barcode)
        if forward_pairs and pair[0] < forward_pairs[-1][0]:
            raise ManifestError("measurement-particle map iteration order is not preserved")
        forward_pairs.append(pair)
        stream.u64(ordinal_index)
        stream.u64(measurement_index)
        _write_barcode(stream, barcode)
    counts["measurement_particles"] = len(forward)
    section_hashes["measurement_particles"] = stream.hexdigest()

    inverse_pairs: list[tuple[tuple[int, int, int, int, int], int]] = []
    inverse = _array(value["particle_measurements"], "event.particle_measurements")
    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("particle_measurements")
    stream.u64(len(inverse))
    for ordinal_index, raw in enumerate(inverse):
        row = _keys(raw, "particle_measurements row", {"ordinal", "barcode", "measurement_index"})
        if row["ordinal"] != ordinal_index:
            raise ManifestError("particle-measurement relation ordinals are malformed")
        barcode = _barcode(row["barcode"], "inverse relation barcode")
        measurement_index = _int(row["measurement_index"], "inverse measurement index")
        if barcode not in particle_set or measurement_index >= len(measurements):
            raise ManifestError("particle-measurement relation contains an unresolved identity")
        pair = (barcode, measurement_index)
        if inverse_pairs and pair < inverse_pairs[-1]:
            raise ManifestError("particle-measurement map iteration order is not preserved")
        inverse_pairs.append(pair)
        stream.u64(ordinal_index)
        _write_barcode(stream, barcode)
        stream.u64(measurement_index)
    counts["particle_measurements"] = len(inverse)
    section_hashes["particle_measurements"] = stream.hexdigest()

    if Counter((measurement, barcode) for measurement, barcode in forward_pairs) != Counter(
        (measurement, barcode) for barcode, measurement in inverse_pairs
    ):
        raise ManifestError("truth maps are not exact inverse multisets")

    event_stream = CanonicalStream()
    event_stream.text(CANONICAL_STREAM_ID)
    event_stream.text("event")
    event_stream.u64(event_id)
    for section in EVENT_SECTIONS:
        event_stream.text(section)
        digest = bytes.fromhex(section_hashes[section])
        event_stream.u64(len(digest))
        event_stream._data += digest  # CanonicalStream deliberately owns this buffer.

    return {
        "ordinal": ordinal,
        "event_id": event_id,
        "counts": counts,
        "section_sha256": section_hashes,
        "semantic_sha256": event_stream.hexdigest(),
    }


def semantic_dataset_hash(summaries: Iterable[Mapping[str, Any]]) -> str:
    stream = CanonicalStream()
    stream.text(CANONICAL_STREAM_ID)
    stream.text("dataset")
    values = list(summaries)
    stream.u64(len(values))
    for ordinal, summary in enumerate(values):
        if summary["ordinal"] != ordinal:
            raise ManifestError("dataset event summaries are reordered")
        stream.u64(summary["event_id"])
        digest = bytes.fromhex(summary["semantic_sha256"])
        stream.u64(len(digest))
        stream._data += digest
    return stream.hexdigest()
