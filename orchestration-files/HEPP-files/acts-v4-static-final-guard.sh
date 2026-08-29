#!/usr/bin/env bash
# Final read-only shared-tree and private-overlay guard inside the container.
set -euo pipefail

MODULE_DIR="${1:?task-owned static-v4 module argument is required}"
SHARED_ACTS_SOURCE="${2:?trusted shared ACTS source argument is required}"
IDENTITY_DIR="${3:?private build identity directory is required}"
ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"
EXPECTED_COMMIT=34edd48852f766e1b9d94d3dc996e27476339f1b

if [[ "$(git -C "$SHARED_ACTS_SOURCE" rev-parse HEAD)" != "$EXPECTED_COMMIT" ]]; then
  echo "error: shared ACTS commit changed" >&2
  exit 1
fi
shared_status="$(git -C "$SHARED_ACTS_SOURCE" status --porcelain=v1 --untracked-files=all)"
if [[ -n "$shared_status" && "$shared_status" != "?? configure.log" ]]; then
  printf 'shared_status_begin\n%s\nshared_status_end\n' "$shared_status" >&2
  echo "error: shared ACTS source has unexpected drift" >&2
  exit 1
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

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/apply_overlay.py" verify \
  --source "$ACTS_SOURCE"
PYTHONDONTWRITEBYTECODE=1 python3 - "$MODULE_DIR" "$ACTS_SOURCE" \
  "$ACTS_BUILD_DIR" "$IDENTITY_DIR" <<'PY'
import sys
from pathlib import Path

module, source, build, identities = map(Path, sys.argv[1:])
sys.path.insert(0, str(module))
from identity import validate_private_build

print(validate_private_build(source, build, identities))
PY

dry_run="$(ninja -C "$ACTS_BUILD_DIR" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: final private build has pending work" >&2
  exit 1
fi
python3 - <<'PY'
import acts
import acts.examples
import acts.examples.root

assert tuple(acts.__version__) == (46, 5, 0)
assert hasattr(acts.examples.root, "OwnedSeedingDatasetReader")
assert hasattr(acts.examples.root, "OwnedSeedingDatasetWriter")
assert hasattr(acts.examples.PythonTrackFinderPerformanceWriter, "stats")
print("final_private_import=ok")
PY
printf 'final_guard=passed shared_commit=%s shared_tracked_clean=yes preexisting_untracked=configure.log\n' \
  "$EXPECTED_COMMIT"
