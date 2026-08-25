#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:-$ACTS_SOURCE/build}"
ACTS_VERSION="${ACTS_VERSION:-v46.5.0}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

load_environment() {
  if [[ -f "$ACTS_LCG_SETUP" ]]; then
    local rc
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
    return
  fi

  if ! command -v module >/dev/null 2>&1; then
    for init in /etc/profile.d/modules.sh /usr/share/Modules/init/bash; do
      if [[ -r "$init" ]]; then
        # shellcheck disable=SC1090
        source "$init"
        break
      fi
    done
  fi

  if command -v module >/dev/null 2>&1; then
    module load \
      GCC/12.3.0 \
      CMake/3.26.3-GCCcore-12.3.0 \
      Ninja/1.11.1-GCCcore-12.3.0 \
      Python/3.11.3-GCCcore-12.3.0 \
      ROOT/6.30.06-foss-2023a \
      Eigen/3.4.0-GCCcore-12.3.0
  else
    echo 'warning: no LCG view or environment modules found; using the current shell' >&2
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: required command not found: $1" >&2
    exit 1
  }
}

load_environment
require_command git
require_command cmake
require_command ninja
require_command python3

if [[ ! -d "$ACTS_SOURCE/.git" ]]; then
  echo "error: ACTS source repository not found: $ACTS_SOURCE" >&2
  exit 1
fi

actual_tag="$(git -C "$ACTS_SOURCE" describe --tags --exact-match HEAD 2>/dev/null || true)"
if [[ "$actual_tag" != "$ACTS_VERSION" ]]; then
  echo "error: expected ACTS tag $ACTS_VERSION, found ${actual_tag:-unknown}" >&2
  exit 1
fi

git -C "$ACTS_SOURCE" submodule update --init --recursive

export CC="$(command -v gcc)"
export CXX="$(command -v g++)"
current_cxx="$CXX"
cached_cxx=""
if [[ -f "$ACTS_BUILD_DIR/CMakeCache.txt" ]]; then
  cached_cxx="$(sed -n 's#^CMAKE_CXX_COMPILER:FILEPATH=##p' "$ACTS_BUILD_DIR/CMakeCache.txt")"
fi
if [[ -z "$cached_cxx" && -d "$ACTS_BUILD_DIR/CMakeFiles" ]]; then
  cached_cxx="$(grep -h -m1 '^set(CMAKE_CXX_COMPILER ' "$ACTS_BUILD_DIR"/CMakeFiles/*/CMakeCXXCompiler.cmake 2>/dev/null | sed -n 's#.*\"\(.*\)\".*#\1#p')"
fi
if [[ -n "$cached_cxx" && "$cached_cxx" != "$current_cxx" ]]; then
  echo "removing generated build cache configured with a different compiler: $cached_cxx"
  rm -rf -- "$ACTS_BUILD_DIR"
fi

cmake -S "$ACTS_SOURCE" -B "$ACTS_BUILD_DIR" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DACTS_BUILD_EXAMPLES=ON \
  -DACTS_BUILD_PYTHON_BINDINGS=ON \
  -DACTS_BUILD_EXAMPLES_PYTHIA8=ON \
  -DACTS_BUILD_EXAMPLES_ROOT=ON \
  -DACTS_BUILD_PLUGIN_ROOT=ON \
  -DACTS_BUILD_UNITTESTS=OFF \
  -DACTS_BUILD_EXAMPLES_UNITTESTS=OFF

echo "ACTS $ACTS_VERSION configured at $ACTS_BUILD_DIR"
