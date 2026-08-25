#!/usr/bin/env bash
set -euo pipefail

OPTIMIZATION_ROOT="${1:?optimization root is required}"
RUN_ROOT="${2:?run root is required}"

rm -rf -- "$OPTIMIZATION_ROOT" "$RUN_ROOT"
printf 'ACTS_EVALUATION_CLEANUP_DONE optimization=%s run=%s\n' "$OPTIMIZATION_ROOT" "$RUN_ROOT"
