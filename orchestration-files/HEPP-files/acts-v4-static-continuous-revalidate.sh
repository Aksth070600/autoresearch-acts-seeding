#!/usr/bin/env bash
# Revalidate every immutable revision-2 owned-static campaign input before calibration.
set -euo pipefail

MODULE_DIR="${1:?static-v4 module is required}"
DATASET="${2:?canonical dataset is required}"
GEOMETRY_DIR="${3:?geometry directory is required}"
IDENTITY_DIR="${4:?production identity directory is required}"
TEMPLATE="${5:?immutable Genesis template is required}"
SLOT="${6:?restored Genesis slot is required}"
GENESIS_OPTIMIZATION="${7:?canonical Genesis optimization tree is required}"
QUALIFICATION="${8:?qualification evidence is required}"
PUBLICATION="${9:?publication evidence is required}"
DSO_QUALIFICATION="${10:?fresh loaded-DSO qualification evidence is required}"
OUTPUT="${11:?new revalidation evidence is required}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"
EXPECTED_DATASET="acts-seeding-v4-owned-static-a05ae8663452d52dc2b90e2fa5372091a2cb04feb8cce86646da9f6ccbc2f3fb"
EXPECTED_RUNNER="0cf74c9197df006d28eabbaf197b490f8e8ae9c27f110cd1b42af4c40718b12c"

if [[ -e "$OUTPUT" || ! -d "$TEMPLATE" || ! -d "$SLOT" || ! -f "$ACTS_LCG_SETUP" ]]; then
  echo "error: output exists or immutable campaign inputs are incomplete" >&2
  exit 2
fi
if [[ "$(basename -- "$DATASET")" != "$EXPECTED_DATASET" ]]; then
  echo "error: canonical dataset locator differs" >&2
  exit 2
fi
if [[ ! -O "$DATASET" || -L "$DATASET" ]] || find "$DATASET" -type f -perm /222 -print -quit | grep -q .; then
  echo "error: canonical dataset is not user-owned read-only material" >&2
  exit 2
fi
if find "$TEMPLATE" -type f -perm /222 -print -quit | grep -q .; then
  echo "error: immutable Genesis template retained writable files" >&2
  exit 2
fi

unset CC CXX FC
set +e +u
# shellcheck disable=SC1090
source "$ACTS_LCG_SETUP"
setup_rc=$?
set -e -u
if (( setup_rc != 0 )); then
  echo "error: pinned LCG setup failed: $setup_rc" >&2
  exit 1
fi
set +u
# shellcheck disable=SC1090,SC1091
source "$SLOT/build/python/setup.sh"
set -u

ACTS_SOURCE="$SLOT/source"
ACTS_BUILD_DIR="$SLOT/build"
export ACTS_SOURCE ACTS_BUILD_DIR
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/apply_overlay.py" verify --source "$ACTS_SOURCE" >/dev/null
python3 - "$MODULE_DIR" "$DATASET" "$GEOMETRY_DIR" "$IDENTITY_DIR" "$TEMPLATE" \
  "$SLOT" "$GENESIS_OPTIMIZATION" "$QUALIFICATION" "$PUBLICATION" \
  "$DSO_QUALIFICATION" "$OUTPUT" "$EXPECTED_RUNNER" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

(
    module,
    dataset,
    geometry,
    identities,
    template,
    slot,
    genesis,
    qualification_path,
    publication_path,
    dso_qualification_path,
    output,
) = map(Path, sys.argv[1:12])
expected_runner = sys.argv[12]
sys.path.insert(0, str(module))
from identity import input_identities, source_file_identities, validate_private_build
from schema import (
    ACTS_COMMIT,
    CANONICAL_PROJECT_GENESIS_COMMIT,
    CANONICAL_PROTOCOL_ID,
    PILOT_PROTOCOL_REVISION,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_dataset_directory,
)

manifest, detached = validate_dataset_directory(
    dataset,
    expected_protocol_id=CANONICAL_PROTOCOL_ID,
    expected_dataset_id=dataset.name,
    expected_events=50,
)
qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
publication = json.loads(publication_path.read_text(encoding="utf-8"))
dso_qualification = json.loads(dso_qualification_path.read_text(encoding="utf-8"))
if qualification.get("all_gates_passed") is not True:
    raise SystemExit("canonical qualification evidence did not pass all gates")
qualification_sha = sha256_file(qualification_path)
if (
    publication.get("dataset_id") != dataset.name
    or publication.get("manifest_sha256") != detached["manifest.json"]
    or publication.get("payload_sha256") != detached["payload.root"]
    or publication.get("qualification_evidence_sha256") != qualification_sha
):
    raise SystemExit("publication evidence differs from canonical bytes")
if (
    dso_qualification.get("protocol_revision") != PILOT_PROTOCOL_REVISION
    or dso_qualification.get("complete_private_closure_passed") is not True
    or dso_qualification.get("external_acts_object_rejection_passed") is not True
    or dso_qualification.get("loaded_acts_object_count") != len(dso_qualification.get("loaded_acts_dsos", {}))
):
    raise SystemExit("fresh complete loaded-DSO qualification differs")
for relative, digest in dso_qualification["loaded_acts_dsos"].items():
    if sha256_file(slot / "build" / relative) != digest:
        raise SystemExit(f"fresh loaded-DSO qualification artifact differs: {relative}")
if manifest["production"]["project_genesis_commit"] != CANONICAL_PROJECT_GENESIS_COMMIT:
    raise SystemExit("dataset scientific Genesis differs")
if manifest["production"]["acts"]["commit"] != ACTS_COMMIT:
    raise SystemExit("dataset ACTS commit differs")

build_identity = validate_private_build(slot / "source", slot / "build", identities)
for key, value in build_identity.items():
    if manifest["identities"][key] != value:
        raise SystemExit(f"restored Genesis build identity differs: {key}")
for key, value in input_identities(geometry).items():
    if manifest["identities"][key] != value:
        raise SystemExit(f"geometry or configuration identity differs: {key}")
for key in ("writer_source_sha256", "reader_source_sha256"):
    if manifest["identities"][key] != source_file_identities()[key]:
        raise SystemExit(f"owned source identity differs: {key}")

optimization_hashes = {}
for path in sorted(genesis.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(genesis)
    source_path = slot / "source" / relative
    template_path = template / "source" / relative
    if source_path.read_bytes() != path.read_bytes() or template_path.read_bytes() != path.read_bytes():
        raise SystemExit(f"Genesis optimization content differs: {relative}")
    optimization_hashes[relative.as_posix()] = sha256_file(path)
if len(optimization_hashes) != 27:
    raise SystemExit("canonical Genesis optimization file count differs")
runner_sha = sha256_file(module / "run_static.py")
if runner_sha != expected_runner:
    raise SystemExit("protocol revision 2 runner identity differs")

value = {
    "schema": "acts-v4-owned-static-continuous-revalidation-v1",
    "protocol_id": CANONICAL_PROTOCOL_ID,
    "protocol_revision": PILOT_PROTOCOL_REVISION,
    "dataset_id": dataset.name,
    "acts_commit": ACTS_COMMIT,
    "scientific_genesis_commit": CANONICAL_PROJECT_GENESIS_COMMIT,
    "checks": {
        "canonical_dataset_bytes": True,
        "canonical_manifest": True,
        "user_owned_read_only_publication": True,
        "publication_permissions": True,
        "qualification_all_gates": True,
        "optimization_genesis_content": True,
        "protocol_revision_2_runner": True,
        "immutable_template": True,
        "private_source_build_identity": True,
        "geometry_field_configuration_identity": True,
        "owned_reader_writer_identity": True,
        "complete_loaded_dso_closure": True,
        "external_acts_object_rejection": True,
    },
    "identities": {
        "manifest_sha256": detached["manifest.json"],
        "payload_sha256": detached["payload.root"],
        "qualification_evidence_sha256": qualification_sha,
        "runner_sha256": runner_sha,
        "source_manifest_sha256": build_identity["source_manifest_sha256"],
        "build_manifest_sha256": build_identity["build_manifest_sha256"],
        "overlay_manifest_sha256": build_identity["overlay_manifest_sha256"],
        "optimization_tree_sha256": sha256_bytes(canonical_json_bytes(optimization_hashes)),
        "loaded_dso_qualification_sha256": sha256_file(dso_qualification_path),
        "loaded_dso_manifest_sha256": dso_qualification["loaded_dso_manifest_sha256"],
    },
    "paths": {
        "dataset": str(dataset.resolve()),
        "template": str(template.resolve()),
        "slot": str(slot.resolve()),
    },
}
value["revalidation_sha256"] = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
atomic_write_json(output, value)
print(f"continuous_revalidation={output}")
print(f"continuous_revalidation_sha256={value['revalidation_sha256']}")
PY

dry_run="$(ninja -C "$SLOT/build" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: restored Genesis target has pending work" >&2
  exit 1
fi
python3 - <<'PY'
import acts
import acts.examples
import acts.examples.root
assert tuple(acts.__version__) == (46, 5, 0)
assert hasattr(acts.examples.root, "OwnedSeedingDatasetReader")
assert hasattr(acts.examples.PythonTrackFinderPerformanceWriter, "stats")
print("continuous_runtime_import=passed")
PY
chmod 0440 "$OUTPUT"
printf 'continuous_revalidation=passed protocol_revision=2 dataset=%s\n' "$EXPECTED_DATASET"
