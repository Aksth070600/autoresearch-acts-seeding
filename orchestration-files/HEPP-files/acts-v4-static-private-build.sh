#!/usr/bin/env bash
# Task-owned entry point for the acts-hepp02 AlmaLinux tmux container.
set -euo pipefail

SHARED_ACTS_SOURCE="${1:?trusted shared ACTS source argument is required}"
MODULE_DIR="${2:?task-owned static-v4 module argument is required}"
ACTS_SOURCE="${ACTS_SOURCE:?ACTS_SOURCE must name the private source path}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?ACTS_BUILD_DIR must name the private build path}"
ACTS_BUILD_JOBS="${ACTS_BUILD_JOBS:-8}"

private_root="$(dirname -- "$ACTS_SOURCE")"
if [[ "$ACTS_SOURCE" != "$private_root/source" ]]; then
  echo "error: ACTS_SOURCE must be the source directory under one private root" >&2
  exit 2
fi
if [[ "$ACTS_BUILD_DIR" != "$private_root/build" ]]; then
  echo "error: ACTS_BUILD_DIR must be the build directory beside ACTS_SOURCE" >&2
  exit 2
fi
if [[ ! -f "$MODULE_DIR/build_private.sh" ]]; then
  echo "error: task-owned static-v4 module is missing: $MODULE_DIR" >&2
  exit 2
fi

printf 'container_private_build source=%s build=%s jobs=%s\n' \
  "$ACTS_SOURCE" "$ACTS_BUILD_DIR" "$ACTS_BUILD_JOBS"
SHARED_ACTS_SOURCE="$SHARED_ACTS_SOURCE" \
PRIVATE_ROOT="$private_root" \
ACTS_BUILD_JOBS="$ACTS_BUILD_JOBS" \
bash "$MODULE_DIR/build_private.sh"
