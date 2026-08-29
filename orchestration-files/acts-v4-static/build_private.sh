#!/usr/bin/env bash
# Build the project overlay in a new private ACTS v46.5.0 copy.
set -euo pipefail

MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SHARED_ACTS_SOURCE="${SHARED_ACTS_SOURCE:?set SHARED_ACTS_SOURCE to the read-only trusted ACTS copy}"
PRIVATE_ROOT="${PRIVATE_ROOT:?set PRIVATE_ROOT to a new task-owned directory}"
ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ ! "$ACTS_BUILD_JOBS" =~ ^[1-8]$ ]]; then
  echo "error: ACTS_BUILD_JOBS must be an integer from 1 through 8" >&2
  exit 2
fi
if [[ -e "$PRIVATE_ROOT" ]]; then
  echo "error: PRIVATE_ROOT already exists: $PRIVATE_ROOT" >&2
  exit 2
fi
if [[ ! -d "$SHARED_ACTS_SOURCE/.git" ]]; then
  echo "error: trusted ACTS repository not found: $SHARED_ACTS_SOURCE" >&2
  exit 2
fi
shared_real="$(cd -- "$SHARED_ACTS_SOURCE" && pwd -P)"
parent="$(dirname -- "$PRIVATE_ROOT")"
mkdir -p -- "$parent"
parent_real="$(cd -- "$parent" && pwd -P)"
private_real="$parent_real/$(basename -- "$PRIVATE_ROOT")"
if [[ "$private_real" == "$shared_real" || "$private_real" == "$shared_real"/* || "$shared_real" == "$private_real"/* ]]; then
  echo "error: private and shared ACTS paths overlap" >&2
  exit 2
fi
if [[ "$(git -C "$shared_real" rev-parse HEAD)" != "34edd48852f766e1b9d94d3dc996e27476339f1b" ]]; then
  echo "error: trusted ACTS source commit mismatch" >&2
  exit 2
fi

printf 'private_build_phase=copy source=%s destination=%s\n' "$shared_real" "$private_real"
mkdir -- "$private_real"
cp -a --reflink=always -- "$shared_real" "$private_real/source"
mkdir -- "$private_real/deps"
for dependency in pybind11-src nlohmann_json-src; do
  if [[ ! -d "$private_real/source/build/_deps/$dependency" ]]; then
    echo "error: trusted local dependency is missing: $dependency" >&2
    exit 2
  fi
  cp -a --reflink=always -- \
    "$private_real/source/build/_deps/$dependency" \
    "$private_real/deps/$dependency"
done
# This is a newly created private copy. Its configured shared build contains
# absolute shared paths and must never be reused at the new logical path.
rm -rf -- "$private_real/source/build"
rm -f -- "$private_real/source/configure.log"

if [[ -f "$ACTS_LCG_SETUP" ]]; then
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
else
  echo "error: pinned LCG setup is unavailable: $ACTS_LCG_SETUP" >&2
  exit 2
fi
CC="$(command -v gcc)"
CXX="$(command -v g++)"
export CC CXX

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/apply_overlay.py" apply \
  --source "$private_real/source"

printf 'private_build_phase=configure jobs=%s\n' "$ACTS_BUILD_JOBS"
cmake -S "$private_real/source" -B "$private_real/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DACTS_BUILD_EXAMPLES=ON \
  -DACTS_BUILD_PYTHON_BINDINGS=ON \
  -DACTS_BUILD_EXAMPLES_PYTHIA8=ON \
  -DACTS_BUILD_EXAMPLES_ROOT=ON \
  -DACTS_BUILD_PLUGIN_ROOT=ON \
  -DACTS_BUILD_UNITTESTS=OFF \
  -DACTS_BUILD_EXAMPLES_UNITTESTS=OFF \
  -DFETCHCONTENT_FULLY_DISCONNECTED=ON \
  -DFETCHCONTENT_SOURCE_DIR_PYBIND11="$private_real/deps/pybind11-src" \
  -DFETCHCONTENT_SOURCE_DIR_NLOHMANN_JSON="$private_real/deps/nlohmann_json-src"

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/invalidate_build.py" \
  --source "$private_real/source" \
  --build "$private_real/build" \
  --evidence "$private_real/ninja-invalidation.json"

printf 'private_build_phase=build target=ActsPythonBindings jobs=%s\n' "$ACTS_BUILD_JOBS"
cmake --build "$private_real/build" --target ActsPythonBindings \
  --parallel "$ACTS_BUILD_JOBS"

dry_run="$(ninja -C "$private_real/build" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: post-build Ninja dry run found pending work" >&2
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/write_build_identity.py" \
  --source "$private_real/source" \
  --build "$private_real/build" \
  --output "$private_real/identities"

set +u
# shellcheck disable=SC1090,SC1091
source "$private_real/build/python/setup.sh"
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

printf 'private_build_complete root=%s jobs=%s\n' "$private_real" "$ACTS_BUILD_JOBS"
