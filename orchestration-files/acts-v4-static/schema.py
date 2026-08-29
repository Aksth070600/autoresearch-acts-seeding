#!/usr/bin/env python3
"""Strict qualification manifest and detached-hash validation.

The manifest describes qualification input only. It cannot authorize a canonical
payload or publish campaign evidence. Payload semantics use the independent
canonical stream defined in ``semantic.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

MANIFEST_SCHEMA_ID = "acts-owned-seeding-dataset-v1"
MANIFEST_SCHEMA_VERSION = 1
CANONICAL_STREAM_ID = "acts-owned-seeding-canonical-v1"
PROVISIONAL_PROTOCOL_PREFIX = "acts-seeding-v4-owned-static-test"
CANONICAL_PROTOCOL_ID = "acts-seeding-v4-owned-static"
CANONICAL_PROJECT_GENESIS_COMMIT = "5ed3b47329ceda4edaab48b1efc3c5635f361a30"
CANONICAL_DATASET_ID_PLACEHOLDER = f"{CANONICAL_PROTOCOL_ID}-{'0' * 64}"
ACTS_TAG = "v46.5.0"
ACTS_COMMIT = "34edd48852f766e1b9d94d3dc996e27476339f1b"
EVENT_SECTIONS = (
    "measurements",
    "space_points",
    "particles",
    "selected_particles",
    "measurement_particles",
    "particle_measurements",
)
UNRESOLVED_CAPTAIN_DECISIONS = (
    "canonical-genesis-commit",
    "immutable-production-locator",
    "storage-ownership",
    "root-compression",
    "final-protocol-and-dataset-ids",
    "publication-actor",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,126}[a-z0-9]$")


class ManifestError(ValueError):
    """The dataset contract is malformed or does not match the expected identity."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one accepted UTF-8 representation for a JSON value."""
    try:
        text = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ManifestError(f"value is not canonical JSON: {error}") from error
    return (text + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Hash the complete canonical manifest with its self-referential ID normalized."""
    normalized = json.loads(canonical_json_bytes(manifest))
    try:
        normalized["dataset"]["id"] = CANONICAL_DATASET_ID_PLACEHOLDER
    except (KeyError, TypeError) as error:
        raise ManifestError("canonical manifest lacks dataset identity") from error
    return sha256_bytes(canonical_json_bytes(normalized))


def canonical_dataset_id(manifest: Mapping[str, Any]) -> str:
    """Derive the immutable dataset ID from the normalized complete manifest."""
    return f"{CANONICAL_PROTOCOL_ID}-{canonical_manifest_digest(manifest)}"


def _object(value: Any, path: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{path} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ManifestError(f"{path} keys differ: missing={missing}, extra={extra}")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{path} must be an array")
    return value


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise ManifestError(f"{path} must be a{' non-empty' if nonempty else ''} string")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ManifestError(f"{path} must be an integer >= {minimum}")
    return value


def _sha(value: Any, path: str) -> str:
    text = _string(value, path)
    if _SHA256.fullmatch(text) is None:
        raise ManifestError(f"{path} must be a lowercase SHA-256")
    return text


def _git_sha(value: Any, path: str) -> str:
    text = _string(value, path)
    if _GIT_SHA.fullmatch(text) is None:
        raise ManifestError(f"{path} must be a lowercase full Git SHA")
    return text


def _identity(value: Any, path: str) -> str:
    text = _string(value, path)
    if _ID.fullmatch(text) is None:
        raise ManifestError(f"{path} is not a stable identifier")
    return text


def _strict_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise ManifestError(f"{path} must be a boolean")
    return value


def validate_manifest(
    manifest: Any,
    *,
    expected_protocol_id: str | None = None,
    expected_dataset_id: str | None = None,
    expected_events: int | None = None,
) -> dict[str, Any]:
    """Validate the complete v1 qualification manifest without coercion."""
    root = _object(
        manifest,
        "$",
        {
            "schema",
            "qualification",
            "protocol",
            "dataset",
            "payload",
            "production",
            "identities",
            "contracts",
        },
    )

    schema = _object(root["schema"], "$.schema", {"id", "version", "canonical_stream"})
    if schema["id"] != MANIFEST_SCHEMA_ID:
        raise ManifestError("$.schema.id is unsupported")
    if schema["version"] != MANIFEST_SCHEMA_VERSION:
        raise ManifestError("$.schema.version is unsupported")
    if schema["canonical_stream"] != CANONICAL_STREAM_ID:
        raise ManifestError("$.schema.canonical_stream is unsupported")

    qualification = _object(
        root["qualification"],
        "$.qualification",
        {"only", "canonical", "unresolved_captain_decisions"},
    )
    qualification_only = _strict_bool(
        qualification["only"], "$.qualification.only"
    )
    canonical = _strict_bool(
        qualification["canonical"], "$.qualification.canonical"
    )
    decisions = _list(
        qualification["unresolved_captain_decisions"],
        "$.qualification.unresolved_captain_decisions",
    )
    if qualification_only:
        if canonical or decisions != list(UNRESOLVED_CAPTAIN_DECISIONS):
            raise ManifestError(
                "qualification policy was omitted, reordered, or converted to production"
            )
    elif not canonical or decisions:
        raise ManifestError("canonical production must resolve every captain decision")

    protocol = _object(root["protocol"], "$.protocol", {"id", "prefix"})
    protocol_id = _identity(protocol["id"], "$.protocol.id")
    if canonical:
        if protocol != {"id": CANONICAL_PROTOCOL_ID, "prefix": CANONICAL_PROTOCOL_ID}:
            raise ManifestError("canonical protocol identity mismatch")
    else:
        if protocol["prefix"] != PROVISIONAL_PROTOCOL_PREFIX:
            raise ManifestError("$.protocol.prefix is not the provisional static-v4 prefix")
        if protocol_id != PROVISIONAL_PROTOCOL_PREFIX and not protocol_id.startswith(
            PROVISIONAL_PROTOCOL_PREFIX + "-"
        ):
            raise ManifestError("$.protocol.id is outside the static-v4 qualification namespace")
    if expected_protocol_id is not None and protocol_id != expected_protocol_id:
        raise ManifestError("protocol identity mismatch")

    dataset = _object(
        root["dataset"],
        "$.dataset",
        {"id", "event_count", "ordered_event_ids", "events"},
    )
    dataset_id = _identity(dataset["id"], "$.dataset.id")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ManifestError("dataset identity mismatch")
    event_count = _integer(dataset["event_count"], "$.dataset.event_count", minimum=1)
    if expected_events is not None and event_count != expected_events:
        raise ManifestError("event count mismatch")
    event_ids = _list(dataset["ordered_event_ids"], "$.dataset.ordered_event_ids")
    if len(event_ids) != event_count:
        raise ManifestError("ordered event count differs from dataset.event_count")
    for ordinal, event_id in enumerate(event_ids):
        _integer(event_id, f"$.dataset.ordered_event_ids[{ordinal}]")
    if len(set(event_ids)) != len(event_ids):
        raise ManifestError("ordered event IDs contain a duplicate")
    if event_ids != list(range(event_count)):
        raise ManifestError("v1 event IDs must be ordered, contiguous 0..N-1")

    events = _list(dataset["events"], "$.dataset.events")
    if len(events) != event_count:
        raise ManifestError("event summary count differs from dataset.event_count")
    for ordinal, summary_value in enumerate(events):
        summary = _object(
            summary_value,
            f"$.dataset.events[{ordinal}]",
            {"ordinal", "event_id", "counts", "section_sha256", "semantic_sha256"},
        )
        if summary["ordinal"] != ordinal or summary["event_id"] != event_ids[ordinal]:
            raise ManifestError(f"event {ordinal} identity/order mismatch")
        counts = _object(summary["counts"], f"event {ordinal}.counts", set(EVENT_SECTIONS))
        hashes = _object(
            summary["section_sha256"],
            f"event {ordinal}.section_sha256",
            set(EVENT_SECTIONS),
        )
        for section in EVENT_SECTIONS:
            _integer(counts[section], f"event {ordinal}.counts.{section}")
            _sha(hashes[section], f"event {ordinal}.section_sha256.{section}")
        if counts["selected_particles"] > counts["particles"]:
            raise ManifestError(f"event {ordinal} selected particle count exceeds all particles")
        if counts["measurement_particles"] != counts["particle_measurements"]:
            raise ManifestError(f"event {ordinal} truth map multiplicities differ")
        _sha(summary["semantic_sha256"], f"event {ordinal}.semantic_sha256")

    payload = _object(
        root["payload"],
        "$.payload",
        {"file", "sha256", "size_bytes", "root_uuid", "compression"},
    )
    if payload["file"] != "payload.root":
        raise ManifestError("$.payload.file must be payload.root")
    _sha(payload["sha256"], "$.payload.sha256")
    _integer(payload["size_bytes"], "$.payload.size_bytes", minimum=1)
    _string(payload["root_uuid"], "$.payload.root_uuid")
    compression = _object(
        payload["compression"], "$.payload.compression", {"algorithm", "level"}
    )
    if compression["algorithm"] not in ("uncompressed", "lz4", "zstd"):
        raise ManifestError("unsupported qualification compression")
    level = _integer(compression["level"], "$.payload.compression.level")
    if compression["algorithm"] == "uncompressed" and level != 0:
        raise ManifestError("uncompressed payload level must be zero")

    production = _object(
        root["production"],
        "$.production",
        {
            "acts",
            "project_genesis_commit",
            "project_genesis_is_canonical",
            "seed",
            "pileup",
            "events",
            "threads",
            "generator",
            "hard_process",
            "host",
            "container_image_sha256",
            "started_at",
            "finished_at",
            "exit_status",
            "completed_event_ids",
            "unmasked_fpes",
        },
    )
    acts = _object(production["acts"], "$.production.acts", {"tag", "commit"})
    if acts != {"tag": ACTS_TAG, "commit": ACTS_COMMIT}:
        raise ManifestError("ACTS identity mismatch")
    genesis = production["project_genesis_commit"]
    if genesis is not None:
        _git_sha(genesis, "$.production.project_genesis_commit")
    genesis_is_canonical = _strict_bool(
        production["project_genesis_is_canonical"],
        "$.production.project_genesis_is_canonical",
    )
    if canonical:
        if genesis != CANONICAL_PROJECT_GENESIS_COMMIT or not genesis_is_canonical:
            raise ManifestError("canonical project Genesis identity mismatch")
    elif genesis_is_canonical:
        raise ManifestError("qualification cannot select a canonical project Genesis")
    if production["seed"] != 42 or production["pileup"] != 200:
        raise ManifestError("production random contract mismatch")
    if production["events"] != event_count or production["threads"] != 1:
        raise ManifestError("production event/thread contract mismatch")
    if production["generator"] != "Pythia8" or production["hard_process"] != [
        "Top:qqbar2ttbar=on"
    ]:
        raise ManifestError("production generator contract mismatch")
    _string(production["host"], "$.production.host")
    _sha(production["container_image_sha256"], "$.production.container_image_sha256")
    _string(production["started_at"], "$.production.started_at")
    _string(production["finished_at"], "$.production.finished_at")
    if production["exit_status"] != 0:
        raise ManifestError("dataset production did not exit successfully")
    if production["completed_event_ids"] != event_ids:
        raise ManifestError("dataset production completion differs from ordered events")
    _integer(production["unmasked_fpes"], "$.production.unmasked_fpes")

    identities = _object(
        root["identities"],
        "$.identities",
        {
            "source_manifest_sha256",
            "build_manifest_sha256",
            "overlay_manifest_sha256",
            "writer_source_sha256",
            "reader_source_sha256",
            "builder_sha256",
            "geometry_tgeo_sha256",
            "geometry_material_sha256",
            "field_sha256",
            "digitization_sha256",
            "pixel_geometry_selection_sha256",
            "seeding_config_sha256",
        },
    )
    for key, value in identities.items():
        _sha(value, f"$.identities.{key}")

    contracts = _object(
        root["contracts"],
        "$.contracts",
        {
            "truth_payload_scope",
            "selected_particle_marker",
            "pixel_spacepoint_policy",
            "static_expected_unmasked_fpes",
            "performance_output",
            "root_plots",
            "matcher",
        },
    )
    if contracts["truth_payload_scope"] != "all-simulated-particles":
        raise ManifestError("truth payload scope mismatch")
    if contracts["selected_particle_marker"] != "exact-post-digitization-container":
        raise ManifestError("selected marker contract mismatch")
    if contracts["pixel_spacepoint_policy"] != "ordered-pixel-only-one-index-source-link":
        raise ManifestError("pixel space-point contract mismatch")
    if contracts["static_expected_unmasked_fpes"] != 0:
        raise ManifestError("static qualification must expect zero unmasked FPEs")
    if contracts["performance_output"] != "exact-json-collector-stats":
        raise ManifestError("performance output contract mismatch")
    if _strict_bool(contracts["root_plots"], "$.contracts.root_plots"):
        raise ManifestError("ROOT plots must be off for owned-static runs")
    matcher = _object(contracts["matcher"], "$.contracts.matcher", {"matching_ratio", "double_matching"})
    if matcher["matching_ratio"] != 1.0 or _strict_bool(
        matcher["double_matching"], "$.contracts.matcher.double_matching"
    ):
        raise ManifestError("matcher contract mismatch")

    if canonical:
        if event_count != 50:
            raise ManifestError("canonical dataset must contain exactly 50 events")
        if compression != {"algorithm": "lz4", "level": 4}:
            raise ManifestError("canonical dataset must use LZ4 level 4")
        if dataset_id != canonical_dataset_id(root):
            raise ManifestError("canonical dataset ID is not its complete manifest digest")

    # Return a plain object so callers cannot rely on a custom mapping type.
    return dict(root)


def load_manifest(path: Path, **expectations: Any) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"cannot read manifest: {error}") from error
    try:
        manifest = json.loads(raw, parse_constant=lambda token: (_ for _ in ()).throw(
            ManifestError(f"non-finite JSON token: {token}")
        ))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ManifestError(f"manifest is not strict UTF-8 JSON: {error}") from error
    validated = validate_manifest(manifest, **expectations)
    if raw != canonical_json_bytes(validated):
        raise ManifestError("manifest bytes are not canonical JSON")
    return validated


def validate_dataset_directory(
    directory: Path,
    **expectations: Any,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate exact files, detached hashes, manifest, and payload bytes."""
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ManifestError("dataset path is not a directory")
    names = sorted(entry.name for entry in directory.iterdir())
    if names != ["SHA256SUMS", "manifest.json", "payload.root"]:
        raise ManifestError(f"dataset directory has unexpected entries: {names}")

    sums_path = directory / "SHA256SUMS"
    try:
        lines = sums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise ManifestError(f"cannot read SHA256SUMS: {error}") from error
    if len(lines) != 2:
        raise ManifestError("SHA256SUMS must contain exactly two lines")
    detached: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (manifest\.json|payload\.root)", line)
        if match is None or match.group(2) in detached:
            raise ManifestError("SHA256SUMS is malformed or contains a duplicate")
        detached[match.group(2)] = match.group(1)
    if list(detached) != ["manifest.json", "payload.root"]:
        raise ManifestError("SHA256SUMS entries must be sorted by filename")

    for name, expected_hash in detached.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ManifestError(f"{name} must be a regular non-symlink file")
        if sha256_file(path) != expected_hash:
            raise ManifestError(f"detached hash mismatch for {name}")

    manifest = load_manifest(directory / "manifest.json", **expectations)
    payload = directory / "payload.root"
    stat = payload.stat()
    if manifest["payload"]["sha256"] != detached["payload.root"]:
        raise ManifestError("manifest payload hash differs from detached hash")
    if manifest["payload"]["size_bytes"] != stat.st_size:
        raise ManifestError("manifest payload size mismatch")
    return manifest, detached


def atomic_write_json(path: Path, value: Any) -> None:
    """Write canonical JSON by same-directory replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
