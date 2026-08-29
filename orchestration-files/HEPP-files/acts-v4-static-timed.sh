#!/usr/bin/env bash
# Task-owned one-process static latency and strict-result qualification helper.
set -euo pipefail

MODULE_DIR="${1:?task-owned static-v4 module argument is required}"
DATASET="${2:?qualified dataset argument is required}"
WORKSPACE="${3:?new timed workspace is required}"
GEOMETRY_DIR="${4:?pinned ITk geometry directory is required}"
IDENTITY_DIR="${5:?private build identity directory is required}"
PROTOCOL_ID="${6:?provisional protocol ID is required}"
DATASET_ID="${7:?provisional dataset ID is required}"
TOTAL_LATENCY_SECONDS="${8:-}"
ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ -e "$WORKSPACE" ]]; then
  echo "error: timed workspace already exists: $WORKSPACE" >&2
  exit 2
fi
if [[ ! -x /usr/bin/time ]]; then
  echo "error: GNU time is unavailable inside the container" >&2
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
process_log="$WORKSPACE/static-process.log"
time_log="$WORKSPACE/static-process.time-v"
set +e
ACTS_SEQUENCER_FAIL_ON_UNMASKED_FPE=1 \
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -v -o "$time_log" \
  python3 "$MODULE_DIR/run_static.py" \
    --dataset "$DATASET" \
    --geometry-dir "$GEOMETRY_DIR" \
    --private-source "$ACTS_SOURCE" \
    --private-build "$ACTS_BUILD_DIR" \
    --identity-dir "$IDENTITY_DIR" \
    --output-dir "$WORKSPACE/output" \
    --raw-result "$WORKSPACE/raw.json" \
    --protocol-id "$PROTOCOL_ID" \
    --dataset-id "$DATASET_ID" \
    >"$process_log" 2>&1
process_rc=$?
set -e
cat "$process_log"
cat "$time_log"

arguments=(
  --raw "$WORKSPACE/raw.json"
  --timing-csv "$WORKSPACE/output/timing.csv"
  --time-v "$time_log"
  --process-log "$process_log"
  --process-exit-status "$process_rc"
  --output "$WORKSPACE/result.json"
)
if [[ -n "$TOTAL_LATENCY_SECONDS" ]]; then
  arguments+=(--total-latency-seconds "$TOTAL_LATENCY_SECONDS")
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/parse_result.py" "${arguments[@]}"
printf 'timed_static_complete workspace=%s\n' "$WORKSPACE"
