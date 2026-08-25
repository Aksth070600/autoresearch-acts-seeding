#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
BACKUP_ROOT="${1:?backup root is required}"
RUN_ROOT="${2:?run root is required}"
MANIFEST="$RUN_ROOT/originals.tsv"

if [[ ! -f "$MANIFEST" ]]; then
  echo "error: backup manifest not found: $MANIFEST" >&2
  exit 1
fi

while IFS=$'\t' read -r relative_path presence _; do
  [[ -n "$relative_path" ]] || continue
  target_file="$ACTS_SOURCE/$relative_path"
  if [[ "$presence" == present ]]; then
    backup_file="$BACKUP_ROOT/files/$relative_path"
    if [[ ! -f "$backup_file" ]]; then
      echo "error: baseline file missing: $relative_path" >&2
      exit 1
    fi
    mkdir -p "$(dirname "$target_file")"
    cp --preserve=mode,timestamps "$backup_file" "$target_file"
  elif [[ "$presence" == absent ]]; then
    rm -f -- "$target_file"
  else
    echo "error: invalid backup manifest entry: $relative_path" >&2
    exit 1
  fi
done <"$MANIFEST"

source_status="$(git -C "$ACTS_SOURCE" status --porcelain --untracked-files=all | grep -vE '^\?\? configure\.log$' || true)"
if [[ -n "$source_status" ]]; then
  echo "error: ACTS source is not clean after restoration: $ACTS_SOURCE" >&2
  printf '%s\n' "$source_status" >&2
  exit 1
fi
printf 'ACTS_RESTORE_DONE source=%s run=%s\n' "$ACTS_SOURCE" "$RUN_ROOT"
