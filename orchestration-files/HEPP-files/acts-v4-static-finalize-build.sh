#!/usr/bin/env bash
# Final identity and import gate for the task-owned private ACTS build.
set -euo pipefail

MODULE_DIR="${1:?task-owned static-v4 module argument is required}"
PRIVATE_ROOT="${2:?private ACTS root argument is required}"
IDENTITY_OUTPUT="${3:-$PRIVATE_ROOT/identities}"
ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ "$ACTS_SOURCE" != "$PRIVATE_ROOT/source" || "$ACTS_BUILD_DIR" != "$PRIVATE_ROOT/build" ]]; then
  echo "error: private ACTS transport paths do not match PRIVATE_ROOT" >&2
  exit 2
fi
if [[ ! "$ACTS_BUILD_JOBS" =~ ^[1-8]$ ]]; then
  echo "error: ACTS_BUILD_JOBS must be an integer from 1 through 8" >&2
  exit 2
fi
if [[ ! -f "$ACTS_LCG_SETUP" ]]; then
  echo "error: pinned LCG setup is unavailable inside the container" >&2
  exit 2
fi
unset CC CXX FC
set +e +u
# shellcheck disable=SC1090
source "$ACTS_LCG_SETUP"
setup_rc=$?
set -e -u
if (( setup_rc != 0 )); then
  echo "error: LCG setup failed inside the container: $setup_rc" >&2
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/apply_overlay.py" refresh-marker \
  --source "$ACTS_SOURCE"
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/invalidate_build.py" \
  --source "$ACTS_SOURCE" --build "$ACTS_BUILD_DIR" \
  --evidence "$PRIVATE_ROOT/ninja-final-invalidation.json"
cmake --build "$ACTS_BUILD_DIR" --target ActsPythonBindings \
  --parallel "$ACTS_BUILD_JOBS"
dry_run="$(ninja -C "$ACTS_BUILD_DIR" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: post-build Ninja dry run found pending work" >&2
  exit 1
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/write_build_identity.py" \
  --source "$ACTS_SOURCE" --build "$ACTS_BUILD_DIR" \
  --output "$IDENTITY_OUTPUT"

set +u
# shellcheck disable=SC1090,SC1091
source "$ACTS_BUILD_DIR/python/setup.sh"
set -u
python3 - <<'PY'
import acts
import acts.examples
import acts.examples.root

assert tuple(acts.__version__) == (46, 5, 0), acts.__version__
assert hasattr(acts.examples.root, "OwnedSeedingDatasetReader")
assert hasattr(acts.examples.root, "OwnedSeedingDatasetWriter")
assert hasattr(acts.examples, "TrackFinderPerformanceStats")
assert hasattr(acts.examples.PythonTrackFinderPerformanceWriter, "stats")
print("private_import=ok acts=46.5.0 owned_reader_writer=ok exact_stats=ok")
PY
