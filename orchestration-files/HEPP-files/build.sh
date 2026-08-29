#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:-$ACTS_SOURCE/build}"
ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

build_options=()
if (( $# > 1 )); then
  echo 'error: build.sh accepts only --clean-first' >&2
  exit 2
fi
if (( $# == 1 )); then
  if [[ "$1" != --clean-first ]]; then
    echo "error: unsupported build option: $1" >&2
    exit 2
  fi
  build_options+=(--clean-first)
fi

if [[ -f "$ACTS_LCG_SETUP" ]]; then
  unset CC CXX FC
  set +e +u
  # shellcheck disable=SC1090
  source "$ACTS_LCG_SETUP"
  rc=$?
  set -e -u
  if (( rc != 0 )); then
    echo "error: LCG environment setup failed with status $rc: $ACTS_LCG_SETUP" >&2
    exit 1
  fi
fi

if [[ ! -f "$ACTS_BUILD_DIR/CMakeCache.txt" ]]; then
  echo "error: ACTS build directory is not configured: $ACTS_BUILD_DIR" >&2
  echo 'Run: make hepp02-setupActs' >&2
  exit 1
fi

command -v cmake >/dev/null 2>&1 || {
  echo 'error: cmake was not found in the current environment' >&2
  exit 1
}

echo "ACTS build parallel jobs: $ACTS_BUILD_JOBS"
cmake --build "$ACTS_BUILD_DIR" "${build_options[@]}" --parallel "$ACTS_BUILD_JOBS"
echo "ACTS build completed: $ACTS_BUILD_DIR"
