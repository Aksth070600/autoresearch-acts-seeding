#!/usr/bin/env bash
# Task-owned compile-iteration helper for an isolated failed private build.
set -euo pipefail

MODULE_DIR="${1:?task-owned static-v4 module argument is required}"
ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

if [[ ! "$ACTS_BUILD_JOBS" =~ ^[1-8]$ ]]; then
  echo "error: ACTS_BUILD_JOBS must be an integer from 1 through 8" >&2
  exit 2
fi
if [[ ! -f "$ACTS_BUILD_DIR/CMakeCache.txt" || ! -f "$ACTS_BUILD_DIR/build.ninja" ]]; then
  echo "error: isolated private build is not configured" >&2
  exit 2
fi
source_file="$MODULE_DIR/cpp/src/OwnedSeedingDataset.cpp"
header_file="$MODULE_DIR/cpp/include/ActsExamples/Io/Root/OwnedSeedingDataset.hpp"
target_file="$ACTS_SOURCE/Examples/Io/Root/src/OwnedSeedingDataset.cpp"
target_header="$ACTS_SOURCE/Examples/Io/Root/include/ActsExamples/Io/Root/OwnedSeedingDataset.hpp"
compile_root="$MODULE_DIR/compile/Root.cpp"
target_root="$ACTS_SOURCE/Python/Examples/src/plugins/Root.cpp"
compile_particle="$MODULE_DIR/compile/Particle.hpp"
target_particle="$ACTS_SOURCE/Fatras/include/ActsFatras/EventData/Particle.hpp"
if [[ ! -f "$source_file" || ! -f "$header_file" || ! -f "$target_file" || ! -f "$target_header" ]]; then
  echo "error: owned source/header file is missing" >&2
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

cp -- "$source_file" "$target_file"
cp -- "$header_file" "$target_header"
rm -f -- "$ACTS_BUILD_DIR/Examples/Io/Root/CMakeFiles/ActsExamplesIoRoot.dir/src/OwnedSeedingDataset.cpp.o"
if [[ -f "$compile_root" ]]; then
  cp -- "$compile_root" "$target_root"
  rm -f -- "$ACTS_BUILD_DIR/Python/Examples/CMakeFiles/ActsExamplesPythonBindingsRoot.dir/src/plugins/Root.cpp.o"
fi
if [[ -f "$compile_particle" ]] && ! cmp -s -- "$compile_particle" "$target_particle"; then
  cp -- "$compile_particle" "$target_particle"
fi
cmake --build "$ACTS_BUILD_DIR" --target ActsPythonBindings --parallel "$ACTS_BUILD_JOBS"
