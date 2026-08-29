#!/usr/bin/env bash
# Task-owned import check for an already built isolated ACTS overlay.
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

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
