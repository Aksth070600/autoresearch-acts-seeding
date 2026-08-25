#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:-$ACTS_SOURCE/build}"
EVENTS="${1:-1}"
THREADS="${2:-1}"
HIGH_OCCUPANCY="${3:-0}"
RUN_ID="${4:-manual}"

if [[ ! "$EVENTS" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: events must be a positive integer: $EVENTS" >&2
  exit 2
fi
if [[ ! "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: threads must be a positive integer: $THREADS" >&2
  exit 2
fi
if [[ "$HIGH_OCCUPANCY" != 0 && "$HIGH_OCCUPANCY" != 1 ]]; then
  echo "error: high occupancy must be 0 or 1: $HIGH_OCCUPANCY" >&2
  exit 2
fi
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "error: run id contains unsupported characters: $RUN_ID" >&2
  exit 2
fi

runner="HEPP-files/itk_seeding_configurable.py"
if [[ ! -f "$runner" ]]; then
  echo "error: configurable ITk seeding runner not found: $runner" >&2
  exit 1
fi

tmp_root="$(mktemp -d "/tmp/acts-itk-seeding.${RUN_ID}.XXXXXX")"
cleanup() {
  rm -rf -- "$tmp_root"
}
trap cleanup EXIT

printf 'ACTS_ITK_SEEDING_START[%s] events=%s threads=%s high_occupancy=%s\n' \
  "$RUN_ID" "$EVENTS" "$THREADS" "$HIGH_OCCUPANCY"

set +e +u
source HEPP-files/setup.sh
setup_rc=$?
set -e -u
if (( setup_rc != 0 )); then
  printf 'ACTS_ITK_SEEDING_DONE[%s] rc=%s\n' "$RUN_ID" "$setup_rc"
  exit "$setup_rc"
fi

args=(
  --events "$EVENTS"
  --threads "$THREADS"
  --output-dir "$tmp_root/output"
)
if [[ "$HIGH_OCCUPANCY" == 1 ]]; then
  args+=(--high-occupancy)
fi

set +e
python3 "$runner" "${args[@]}"
run_rc=$?
set -e
printf 'ACTS_ITK_SEEDING_DONE[%s] rc=%s\n' "$RUN_ID" "$run_rc"
exit "$run_rc"
