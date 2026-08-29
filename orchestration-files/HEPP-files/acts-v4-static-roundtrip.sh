#!/usr/bin/env bash
# Task-owned one/50-event generated-to-static exact equality helper.
set -euo pipefail

MODULE_DIR="${1:?task-owned static-v4 module argument is required}"
WORKSPACE="${2:?new task-owned qualification workspace is required}"
GEOMETRY_DIR="${3:?pinned ITk geometry directory is required}"
IDENTITY_DIR="${4:?private build identity directory is required}"
PROTOCOL_ID="${5:?provisional protocol ID is required}"
DATASET_ID="${6:?provisional dataset ID is required}"
EVENTS="${7:?event count is required}"
COMPRESSION="${8:?compression setting is required}"
COMPRESSION_LEVEL="${9:?compression level is required}"
ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ -e "$WORKSPACE" ]]; then
  echo "error: qualification workspace already exists: $WORKSPACE" >&2
  exit 2
fi
if [[ ! "$EVENTS" =~ ^(1|50)$ ]]; then
  echo "error: round-trip event count must be 1 or 50" >&2
  exit 2
fi
if [[ ! -f "$ACTS_LCG_SETUP" || ! -f "$ACTS_BUILD_DIR/python/setup.sh" ]]; then
  echo "error: pinned container environment or private Python build is missing" >&2
  exit 2
fi
unset CC CXX FC
set +e +u
# shellcheck disable=SC1090
source "$ACTS_LCG_SETUP"
setup_rc=$?
set -e
if (( setup_rc != 0 )); then
  echo "error: LCG setup failed inside the container: $setup_rc" >&2
  exit 1
fi
# shellcheck disable=SC1090,SC1091
source "$ACTS_BUILD_DIR/python/setup.sh"
set -u

mkdir -p -- "$WORKSPACE"
staging="$WORKSPACE/generation-staging"
dataset="$WORKSPACE/dataset"
generation_log="$WORKSPACE/generation.log"
static_log="$WORKSPACE/static.log"

set +e
ACTS_SEQUENCER_FAIL_ON_UNMASKED_FPE=0 \
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/build_dataset.py" \
  --events "$EVENTS" \
  --staging "$staging" \
  --geometry-dir "$GEOMETRY_DIR" \
  --private-source "$ACTS_SOURCE" \
  --private-build "$ACTS_BUILD_DIR" \
  --identity-dir "$IDENTITY_DIR" \
  --protocol-id "$PROTOCOL_ID" \
  --dataset-id "$DATASET_ID" \
  --compression "$COMPRESSION" \
  --compression-level "$COMPRESSION_LEVEL" \
  --container-image-sha256 514a5c2c01f33371da3ff78f9806a293ac5cc7d175a022ced4a16c8d5ed5e8d8 \
  >"$generation_log" 2>&1
generation_rc=$?
set -e
cat "$generation_log"
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/finalize_dataset.py" \
  --staging "$staging" \
  --destination "$dataset" \
  --process-log "$generation_log" \
  --process-exit-status "$generation_rc"

set +e
ACTS_SEQUENCER_FAIL_ON_UNMASKED_FPE=1 \
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/run_static.py" \
  --dataset "$dataset" \
  --geometry-dir "$GEOMETRY_DIR" \
  --private-source "$ACTS_SOURCE" \
  --private-build "$ACTS_BUILD_DIR" \
  --identity-dir "$IDENTITY_DIR" \
  --output-dir "$WORKSPACE/static-output" \
  --raw-result "$WORKSPACE/static-raw.json" \
  --protocol-id "$PROTOCOL_ID" \
  --dataset-id "$DATASET_ID" \
  >"$static_log" 2>&1
static_rc=$?
set -e
cat "$static_log"
if (( static_rc != 0 )); then
  echo "error: static process failed: $static_rc" >&2
  exit "$static_rc"
fi

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/compare_generated_static.py" \
  --generated "$staging/generated-raw.json" \
  --static "$WORKSPACE/static-raw.json" \
  --static-diagnostics "$WORKSPACE/static-output/diagnostics.json" \
  --output "$WORKSPACE/exact-equality.json"
printf 'roundtrip_complete events=%s workspace=%s\n' "$EVENTS" "$WORKSPACE"
