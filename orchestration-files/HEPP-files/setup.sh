#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo 'error: source this file instead: source orchestration-files/HEPP-files/setup.sh' >&2
  exit 2
fi

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:-$ACTS_SOURCE/build}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"

export ACTS_SOURCE ACTS_BUILD_DIR

if [[ -f "$ACTS_LCG_SETUP" ]]; then
  __acts_setup_old_opts="$(set +o)"
  unset CC CXX FC
  set +e +u
  # shellcheck disable=SC1090
  source "$ACTS_LCG_SETUP"
  __acts_setup_rc=$?
  eval "$__acts_setup_old_opts"
  if (( __acts_setup_rc != 0 )); then
    echo "error: LCG environment setup failed with status $__acts_setup_rc: $ACTS_LCG_SETUP" >&2
    return 1
  fi
else
  for init in /etc/profile.d/modules.sh /usr/share/Modules/init/bash; do
    if ! command -v module >/dev/null 2>&1 && [[ -r "$init" ]]; then
      # shellcheck disable=SC1090
      source "$init"
      break
    fi
  done

  if command -v module >/dev/null 2>&1; then
    module load \
      GCC/12.3.0 \
      CMake/3.26.3-GCCcore-12.3.0 \
      Ninja/1.11.1-GCCcore-12.3.0 \
      Python/3.11.3-GCCcore-12.3.0 \
      ROOT/6.30.06-foss-2023a \
      Eigen/3.4.0-GCCcore-12.3.0
  fi
fi

python_setup="$ACTS_BUILD_DIR/python/setup.sh"
if [[ ! -f "$python_setup" ]]; then
  echo "error: ACTS Python setup not found: $python_setup" >&2
  echo 'Run: make hepp02-setupActs && make hepp02-build' >&2
  return 1
fi

# shellcheck disable=SC1090
source "$python_setup"

python3 - <<'PY'
import acts
print(f"ACTS Python bindings loaded: {getattr(acts, '__version__', 'unknown')}")
PY
