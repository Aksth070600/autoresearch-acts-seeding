#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
OPTIMIZATION_ROOT="${1:?optimization root is required}"

if [[ ! -d "$OPTIMIZATION_ROOT" ]]; then
  echo "error: optimization files not found: $OPTIMIZATION_ROOT" >&2
  exit 1
fi

while IFS= read -r -d '' optimized_file; do
  relative_path="${optimized_file#"$OPTIMIZATION_ROOT/"}"
  if [[ "$relative_path" == "$optimized_file" || "$relative_path" == ..* || "$relative_path" == */../* ]]; then
    echo "error: unsafe optimization path: $relative_path" >&2
    exit 1
  fi
  target_file="$ACTS_SOURCE/$relative_path"
  mkdir -p "$(dirname "$target_file")"
  cp --preserve=mode,timestamps "$optimized_file" "$target_file"
done < <(find "$OPTIMIZATION_ROOT" -type f -print0 | sort -z)

printf 'ACTS_OPTIMIZATION_APPLIED source=%s root=%s\n' "$ACTS_SOURCE" "$OPTIMIZATION_ROOT"
