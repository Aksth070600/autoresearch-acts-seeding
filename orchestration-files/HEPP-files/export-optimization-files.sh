#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OPTIMIZATION_ROOT="${1:-$PROJECT_ROOT/optimization-files}"
REMOTE_ROOT="${2:?remote optimization root is required}"
HEPP_HOST="${HEPP_HOST:-thomaaks@hepp02.hpc.uio.no}"

if [[ ! -d "$OPTIMIZATION_ROOT" ]]; then
  echo "error: optimization directory not found: $OPTIMIZATION_ROOT" >&2
  exit 1
fi

ssh "$HEPP_HOST" "mkdir -p '$REMOTE_ROOT'"
tar -C "$OPTIMIZATION_ROOT" -cf - . | ssh "$HEPP_HOST" "tar -C '$REMOTE_ROOT' -xf -"
printf 'Optimization files exported to %s:%s\n' "$HEPP_HOST" "$REMOTE_ROOT"
