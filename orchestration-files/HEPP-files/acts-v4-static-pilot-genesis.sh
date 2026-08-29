#!/usr/bin/env bash
# Run five independent canonical Genesis processes and derive one fixed envelope.
set -euo pipefail

MODULE_DIR="${1:?static-v4 module is required}"
DATASET="${2:?canonical dataset is required}"
WORKSPACE="${3:?new Genesis workspace is required}"
GEOMETRY_DIR="${4:?geometry directory is required}"
IDENTITY_DIR="${5:?production identity directory is required}"
GENESIS_ROOT="${6:?prebuilt Genesis root is required}"
CORRECTIONS="${7:?pilot correction evidence is required}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ ! -f "$GENESIS_ROOT/build/python/setup.sh" ]]; then
  echo "error: prebuilt Genesis is missing" >&2
  exit 2
fi
if [[ -e "$WORKSPACE" && ! -d "$WORKSPACE" ]]; then
  echo "error: Genesis workspace is not a directory" >&2
  exit 2
fi
ACTS_SOURCE="$GENESIS_ROOT/source"
ACTS_BUILD_DIR="$GENESIS_ROOT/build"
export ACTS_SOURCE ACTS_BUILD_DIR
lock_path="$(dirname -- "$GENESIS_ROOT")/.campaign.lock"
exec 9>"$lock_path"
flock 9
mkdir -p -- "$WORKSPACE"

unset CC CXX FC
set +e +u
# shellcheck disable=SC1090
source "$ACTS_LCG_SETUP"
setup_rc=$?
set -e
if (( setup_rc != 0 )); then
  echo "error: LCG setup failed: $setup_rc" >&2
  exit 1
fi
# shellcheck disable=SC1090,SC1091
source "$ACTS_BUILD_DIR/python/setup.sh"
set -u

results=()
for index in 1 2 3 4 5; do
  run="$WORKSPACE/genesis-$index"
  if [[ -f "$run/result.json" ]]; then
    if [[ ! -f "$run/record.json" ]]; then
      recovery_total="$(python3 - "$run/result.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["resources"]["wall_seconds"])
PY
)"
      PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/pilot_record.py" record \
        --result "$run/result.json" --dataset "$DATASET" --candidate Genesis \
        --implementation-commit 5ed3b47329ceda4edaab48b1efc3c5635f361a30 \
        --preparation-seconds 0 --build-seconds 0 --record-preparation-seconds 0 \
        --total-latency-seconds "$recovery_total" --corrections "$CORRECTIONS" \
        --output "$run/record.json"
      chmod 0440 "$run/result.json" "$run/record.json"
      echo "genesis_recovery=index-$index preserved_result=yes rerun=no"
    fi
    results+=(--result "$run/result.json")
    continue
  fi
  if [[ -e "$run" ]]; then
    echo "error: incomplete Genesis process evidence requires guidance: $run" >&2
    exit 1
  fi
  mkdir -- "$run"
  queue_ns="$(date +%s%N)"
  process_log="$run/static-process.log"
  time_log="$run/static-process.time-v"
  set +e
  ACTS_SEQUENCER_FAIL_ON_UNMASKED_FPE=1 PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/time -v -o "$time_log" python3 "$MODULE_DIR/run_static.py" \
    --dataset "$DATASET" --geometry-dir "$GEOMETRY_DIR" \
    --private-source "$ACTS_SOURCE" --private-build "$ACTS_BUILD_DIR" \
    --identity-dir "$IDENTITY_DIR" --output-dir "$run/output" \
    --raw-result "$run/raw.json" --protocol-id acts-seeding-v4-owned-static \
    --dataset-id "$(basename -- "$DATASET")" >"$process_log" 2>&1
  process_rc=$?
  set -e
  cat "$process_log"
  cat "$time_log"
  if (( process_rc != 0 )); then
    printf 'scientific_process_started=yes\nscientific_process_rc=%s\n' "$process_rc" \
      >"$run/SCIENTIFIC_PROCESS_FAILED"
    echo "error: Genesis scientific process $index failed; calibration is invalid" >&2
    exit "$process_rc"
  fi
  PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/parse_result.py" \
    --raw "$run/raw.json" --timing-csv "$run/output/timing.csv" \
    --time-v "$time_log" --process-log "$process_log" \
    --process-exit-status "$process_rc" --output "$run/result.json"
  record_ns="$(date +%s%N)"
  total_seconds="$(python3 -c "print(($record_ns-$queue_ns)/1e9)")"
  PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/pilot_record.py" record \
    --result "$run/result.json" --dataset "$DATASET" --candidate Genesis \
    --implementation-commit 5ed3b47329ceda4edaab48b1efc3c5635f361a30 \
    --preparation-seconds 0 --build-seconds 0 --record-preparation-seconds 0 \
    --total-latency-seconds "$total_seconds" --corrections "$CORRECTIONS" \
    --output "$run/record.json"
  chmod 0440 "$run/result.json" "$run/record.json"
  results+=(--result "$run/result.json")
done
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/pilot_record.py" calibrate \
  "${results[@]}" --output "$WORKSPACE/calibration.json"
chmod 0440 "$WORKSPACE/calibration.json"
printf 'genesis_calibration=%s\n' "$WORKSPACE/calibration.json"
