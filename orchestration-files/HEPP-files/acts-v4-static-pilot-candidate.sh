#!/usr/bin/env bash
# Run one proposal-bound candidate from the immutable Genesis reflink template.
set -euo pipefail

MODULE_DIR="${1:?static-v4 module is required}"
DATASET="${2:?canonical dataset is required}"
WORKSPACE="${3:?new candidate workspace is required}"
GEOMETRY_DIR="${4:?geometry directory is required}"
PRODUCTION_IDENTITY_DIR="${5:?production identity directory is required}"
TEMPLATE="${6:?immutable Genesis template is required}"
SLOT="${7:?task-owned candidate slot is required}"
GENESIS_OPTIMIZATION="${8:?canonical Genesis optimization tree is required}"
CANDIDATE_OPTIMIZATION="${9:?candidate optimization tree is required}"
PROPOSAL="${10:?bound proposal is required}"
IMPLEMENTATION_COMMIT="${11:?candidate implementation commit is required}"
CALIBRATION="${12:?Genesis calibration is required}"
CORRECTIONS="${13:?pilot correction evidence is required}"
ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ ! "$ACTS_BUILD_JOBS" =~ ^[1-8]$ ]]; then
  echo "error: ACTS_BUILD_JOBS must be 1 through 8" >&2
  exit 2
fi
if [[ -e "$WORKSPACE" || ! -d "$TEMPLATE/source" || ! -d "$TEMPLATE/build" || ! -d "$TEMPLATE/deps" ]]; then
  echo "error: workspace exists or Genesis template is incomplete" >&2
  exit 2
fi
if find "$TEMPLATE" -type f -perm /222 -print -quit | grep -q .; then
  echo "error: Genesis template is not read-only" >&2
  exit 2
fi
if [[ ! -f "$ACTS_LCG_SETUP" ]]; then
  echo "error: pinned LCG setup is missing" >&2
  exit 2
fi

unset CC CXX FC
set +e +u
# shellcheck disable=SC1090
source "$ACTS_LCG_SETUP"
setup_rc=$?
set -e -u
if (( setup_rc != 0 )); then
  echo "error: LCG setup failed: $setup_rc" >&2
  exit 1
fi

queue_ns="$(date +%s%N)"
lock_path="$(dirname -- "$TEMPLATE")/.campaign.lock"
exec 9>"$lock_path"
flock 9
mkdir -p -- "$WORKSPACE"

# SLOT is disposable task-owned state. The immutable template is never mutated.
rm -rf -- "$SLOT"
mkdir -p -- "$SLOT"
cp -a --reflink=always -- "$TEMPLATE/source" "$SLOT/source"
cp -a --reflink=always -- "$TEMPLATE/build" "$SLOT/build"
cp -a --reflink=always -- "$TEMPLATE/deps" "$SLOT/deps"
chmod -R u+w -- "$SLOT"
ACTS_SOURCE="$SLOT/source"
ACTS_BUILD_DIR="$SLOT/build"
export ACTS_SOURCE ACTS_BUILD_DIR

mapfile -t genesis_files < <(find "$GENESIS_OPTIMIZATION" -type f -printf '%P\n' | LC_ALL=C sort)
if (( ${#genesis_files[@]} == 0 )); then
  echo "error: canonical Genesis optimization tree is empty" >&2
  exit 2
fi
for relative in "${genesis_files[@]}"; do
  install -m 0644 -- "$GENESIS_OPTIMIZATION/$relative" "$ACTS_SOURCE/$relative"
done
python3 - "$ACTS_SOURCE" "$GENESIS_OPTIMIZATION" "$WORKSPACE/genesis-restoration.json" <<'PY'
import hashlib, json, sys
from pathlib import Path
source, genesis, output = map(Path, sys.argv[1:])
files = sorted(path for path in genesis.rglob("*") if path.is_file())
values = {}
for path in files:
    relative = path.relative_to(genesis)
    candidate = source / relative
    if not candidate.is_file() or candidate.read_bytes() != path.read_bytes():
        raise SystemExit(f"Genesis restoration mismatch: {relative}")
    values[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
output.write_text(json.dumps({"canonical_genesis_restored": True, "files": values}, sort_keys=True, separators=(",", ":")) + "\n")
PY

mapfile -t intended_files < <(python3 - "$PROPOSAL" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
for path in value["intended_files"]:
    print(path)
PY
)
for project_relative in "${intended_files[@]}"; do
  relative="${project_relative#optimization-files/}"
  if [[ "$relative" == "$project_relative" || ! -f "$CANDIDATE_OPTIMIZATION/$relative" ]]; then
    echo "error: candidate input is missing: $project_relative" >&2
    exit 2
  fi
  install -m 0644 -- "$CANDIDATE_OPTIMIZATION/$relative" "$ACTS_SOURCE/$relative"
done

invalidation="$WORKSPACE/ninja-invalidation.json"
invalidation_args=()
for file in "${intended_files[@]}"; do
  invalidation_args+=(--changed-file "$file")
done
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/invalidate_candidate.py" \
  --source "$ACTS_SOURCE" --build "$ACTS_BUILD_DIR" \
  --genesis-tree "$GENESIS_OPTIMIZATION" \
  "${invalidation_args[@]}" --output "$invalidation"

build_start_ns="$(date +%s%N)"
cmake --build "$ACTS_BUILD_DIR" --target ActsPythonBindings --parallel "$ACTS_BUILD_JOBS" \
  >"$WORKSPACE/build.log" 2>&1
build_end_ns="$(date +%s%N)"
cat "$WORKSPACE/build.log"
dry_run="$(ninja -C "$ACTS_BUILD_DIR" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: candidate build has pending work" >&2
  exit 1
fi
build_seconds="$(python3 -c "print(($build_end_ns-$build_start_ns)/1e9)")"
pre_identity_ns="$(date +%s%N)"
pre_identity_seconds="$(python3 -c "print(($pre_identity_ns-$queue_ns)/1e9)")"
identity_dir="$WORKSPACE/candidate-identity"
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/candidate_identity.py" \
  --source "$ACTS_SOURCE" --build "$ACTS_BUILD_DIR" \
  --genesis-tree "$GENESIS_OPTIMIZATION" --proposal "$PROPOSAL" \
  --implementation-commit "$IMPLEMENTATION_COMMIT" --invalidation "$invalidation" \
  --output "$identity_dir" --preparation-build-seconds "$pre_identity_seconds"
preparation_end_ns="$(date +%s%N)"
preparation_seconds="$(python3 -c "print(($preparation_end_ns-$queue_ns)/1e9)")"
proposal_sha256="$(sha256sum "$PROPOSAL" | awk '{print $1}')"

set +u
# shellcheck disable=SC1090,SC1091
source "$ACTS_BUILD_DIR/python/setup.sh"
set -u
process_log="$WORKSPACE/static-process.log"
time_log="$WORKSPACE/static-process.time-v"
set +e
ACTS_SEQUENCER_FAIL_ON_UNMASKED_FPE=1 PYTHONDONTWRITEBYTECODE=1 \
/usr/bin/time -v -o "$time_log" python3 "$MODULE_DIR/run_static.py" \
  --dataset "$DATASET" --geometry-dir "$GEOMETRY_DIR" \
  --private-source "$ACTS_SOURCE" --private-build "$ACTS_BUILD_DIR" \
  --identity-dir "$PRODUCTION_IDENTITY_DIR" \
  --candidate-identity-dir "$identity_dir" --proposal-sha256 "$proposal_sha256" \
  --output-dir "$WORKSPACE/output" --raw-result "$WORKSPACE/raw.json" \
  --protocol-id acts-seeding-v4-owned-static \
  --dataset-id "$(basename -- "$DATASET")" >"$process_log" 2>&1
process_rc=$?
process_end_ns="$(date +%s%N)"
set -e
cat "$process_log"
cat "$time_log"
if (( process_rc != 0 )); then
  printf 'scientific_process_started=yes\nscientific_process_rc=%s\n' "$process_rc" \
    >"$WORKSPACE/SCIENTIFIC_PROCESS_FAILED"
  echo "error: scientific candidate process failed after start; no rerun is allowed" >&2
  exit "$process_rc"
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/parse_result.py" \
  --raw "$WORKSPACE/raw.json" --timing-csv "$WORKSPACE/output/timing.csv" \
  --time-v "$time_log" --process-log "$process_log" --process-exit-status "$process_rc" \
  --output "$WORKSPACE/result.json"

record_start_ns="$(date +%s%N)"
record_prep_seconds="$(python3 -c "print(($record_start_ns-$process_end_ns)/1e9)")"
total_seconds="$(python3 -c "print(($record_start_ns-$queue_ns)/1e9)")"
slot_number="$(python3 - "$PROPOSAL" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["slot"])
PY
)"
candidate_name="$(python3 - "$PROPOSAL" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["candidate"])
PY
)"
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/pilot_record.py" record \
  --result "$WORKSPACE/result.json" --dataset "$DATASET" \
  --candidate "$candidate_name" --slot "$slot_number" \
  --implementation-commit "$IMPLEMENTATION_COMMIT" --proposal "$PROPOSAL" \
  --calibration "$CALIBRATION" --preparation-seconds "$preparation_seconds" \
  --build-seconds "$build_seconds" --record-preparation-seconds "$record_prep_seconds" \
  --total-latency-seconds "$total_seconds" --corrections "$CORRECTIONS" \
  --output "$WORKSPACE/record.json"
chmod 0440 "$WORKSPACE/record.json" "$WORKSPACE/result.json"
printf 'candidate_record=%s\nqueue_to_record_seconds=%s\npreparation_seconds=%s\nbuild_seconds=%s\n' \
  "$WORKSPACE/record.json" "$total_seconds" "$preparation_seconds" "$build_seconds"
