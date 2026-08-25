#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:-$ACTS_SOURCE/build}"
EVENTS="${1:-1}"
WORKLOAD="${2:-ttbar_pu200}"
THREADS="${3:--1}"
SEED="${4:-42}"
PILEUP="${5:-200}"
STAGE="${6:-full}"
METRICS_MODE="${7:-none}"
RUN_ID="${8:-manual}"
TIME_BIN="${ACTS_TIME_BIN:-/usr/bin/time}"

if [[ ! "$EVENTS" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: events must be a positive integer: $EVENTS" >&2
  exit 2
fi
if [[ "$WORKLOAD" != "ttbar_pu200" ]]; then
  echo "error: workload must be ttbar_pu200: $WORKLOAD" >&2
  exit 2
fi
if [[ ! "$PILEUP" =~ ^[1-9][0-9]*$ ]]; then
  echo "error: pileup must be a positive integer: $PILEUP" >&2
  exit 2
fi
if [[ "$STAGE" != "seeding" && "$STAGE" != "full" ]]; then
  echo "error: stage must be seeding or full: $STAGE" >&2
  exit 2
fi
if [[ "$METRICS_MODE" != "none" && "$METRICS_MODE" != "time" ]]; then
  echo "error: metrics mode must be none or time: $METRICS_MODE" >&2
  exit 2
fi
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "error: run id contains unsupported characters: $RUN_ID" >&2
  exit 2
fi
if [[ "$METRICS_MODE" == "time" && ! -x "$TIME_BIN" ]]; then
  echo "error: GNU time not found or not executable: $TIME_BIN" >&2
  exit 1
fi

runner="HEPP-files/full_chain_itk_configurable.py"
if [[ ! -f "$runner" ]]; then
  echo "error: configurable ACTS runner not found: $runner" >&2
  exit 1
fi

tmp_root="$(mktemp -d "/tmp/acts-full-chain-itk.${RUN_ID}.XXXXXX")"
output_dir="$tmp_root/output"
metrics_file="$tmp_root/resource-usage.txt"
cleanup() {
  rm -rf -- "$tmp_root"
}
trap cleanup EXIT

printf 'ACTS_FULL_CHAIN_ITK_START[%s] events=%s workload=%s stage=%s metrics=%s threads=%s seed=%s pileup=%s\n' \
  "$RUN_ID" "$EVENTS" "$WORKLOAD" "$STAGE" "$METRICS_MODE" "$THREADS" "$SEED" "$PILEUP"

set +e +u
source HEPP-files/setup.sh
setup_rc=$?
set -e -u
if (( setup_rc != 0 )); then
  printf 'ACTS_FULL_CHAIN_ITK_DONE[%s] rc=%s\n' "$RUN_ID" "$setup_rc"
  exit "$setup_rc"
fi

runner_args=(
  python3 "$runner"
  --events "$EVENTS"
  --workload "$WORKLOAD"
  --threads "$THREADS"
  --seed "$SEED"
  --pileup "$PILEUP"
  --stage "$STAGE"
  --output-dir "$output_dir"
)
set +e
if [[ "$METRICS_MODE" == "time" ]]; then
  "$TIME_BIN" -v -o "$metrics_file" -- "${runner_args[@]}"
else
  "${runner_args[@]}"
fi
run_rc=$?
set -e
if [[ "$METRICS_MODE" == "time" ]]; then
time_metric() {
  awk -v label="$1" '
    {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      prefix = label ":"
      if (index(line, prefix) == 1) {
        value = substr(line, length(prefix) + 1)
        sub(/^[[:space:]]*/, "", value)
        print value
        exit
      }
    }
  ' "$metrics_file"
}
peak_rss_kb="$(time_metric 'Maximum resident set size (kbytes)')"
user_seconds="$(time_metric 'User time (seconds)')"
system_seconds="$(time_metric 'System time (seconds)')"
elapsed="$(time_metric 'Elapsed (wall clock) time (h:mm:ss or m:ss)')"
  printf 'ACTS_FULL_CHAIN_ITK_METRICS[%s] peak_rss_kb=%s user_seconds=%s system_seconds=%s elapsed=%s\n' \
    "$RUN_ID" "${peak_rss_kb:-unknown}" "${user_seconds:-unknown}" "${system_seconds:-unknown}" "${elapsed:-unknown}"
fi
printf 'ACTS_FULL_CHAIN_ITK_DONE[%s] rc=%s\n' "$RUN_ID" "$run_rc"
exit "$run_rc"
