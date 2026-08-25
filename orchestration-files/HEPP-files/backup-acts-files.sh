#!/usr/bin/env bash
set -euo pipefail

ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
OPTIMIZATION_ROOT="${1:?optimization root is required}"
BACKUP_ROOT="${2:?backup root is required}"
RUN_ROOT="${3:?run root is required}"

if [[ ! -d "$ACTS_SOURCE/.git" ]]; then
  echo "error: ACTS source repository not found: $ACTS_SOURCE" >&2
  exit 1
fi
if [[ ! -d "$OPTIMIZATION_ROOT" ]]; then
  echo "error: optimization files not found: $OPTIMIZATION_ROOT" >&2
  exit 1
fi
source_status="$(git -C "$ACTS_SOURCE" status --porcelain --untracked-files=all | grep -vE '^\?\? configure\.log$' || true)"
if [[ -n "$source_status" ]]; then
  echo "error: ACTS source is not clean before backup: $ACTS_SOURCE" >&2
  printf '%s\n' "$source_status" >&2
  exit 1
fi

mkdir -p "$BACKUP_ROOT/files" "$RUN_ROOT"
current_commit="$(git -C "$ACTS_SOURCE" rev-parse HEAD)"
commit_file="$BACKUP_ROOT/source-commit"
manifest_file="$BACKUP_ROOT/manifest.tsv"

if [[ -f "$commit_file" && "$(<"$commit_file")" != "$current_commit" ]]; then
  rm -rf -- "$BACKUP_ROOT/files"
  mkdir -p "$BACKUP_ROOT/files"
  rm -f -- "$manifest_file"
fi

manifest_tmp="$(mktemp "$RUN_ROOT/manifest.XXXXXX")"
backup_manifest_tmp="$(mktemp "$BACKUP_ROOT/manifest.XXXXXX")"
cleanup() {
  rm -f -- "$manifest_tmp" "$backup_manifest_tmp"
}
trap cleanup EXIT

while IFS= read -r -d '' optimized_file; do
  relative_path="${optimized_file#"$OPTIMIZATION_ROOT/"}"
  if [[ "$relative_path" == "$optimized_file" || "$relative_path" == ..* || "$relative_path" == */../* ]]; then
    echo "error: unsafe optimization path: $relative_path" >&2
    exit 1
  fi

  source_file="$ACTS_SOURCE/$relative_path"
  backup_file="$BACKUP_ROOT/files/$relative_path"
  if [[ -e "$source_file" ]]; then
    if [[ ! -f "$source_file" ]]; then
      echo "error: ACTS target is not a regular file: $relative_path" >&2
      exit 1
    fi
    source_hash="$(sha256sum "$source_file" | awk '{print $1}')"
    if [[ -f "$backup_file" ]]; then
      backup_hash="$(sha256sum "$backup_file" | awk '{print $1}')"
      if [[ "$source_hash" != "$backup_hash" ]]; then
        echo "error: ACTS source differs from its reusable baseline: $relative_path" >&2
        exit 1
      fi
    else
      mkdir -p "$(dirname "$backup_file")"
      cp --preserve=mode,timestamps "$source_file" "$backup_file"
    fi
    printf '%s\tpresent\t%s\n' "$relative_path" "$source_hash" >>"$manifest_tmp"
    printf '%s\tpresent\t%s\n' "$relative_path" "$source_hash" >>"$backup_manifest_tmp"
  else
    printf '%s\tabsent\t-\n' "$relative_path" >>"$manifest_tmp"
    printf '%s\tabsent\t-\n' "$relative_path" >>"$backup_manifest_tmp"
  fi
done < <(find "$OPTIMIZATION_ROOT" -type f -print0 | sort -z)

printf '%s\n' "$current_commit" >"$commit_file"
mv -- "$backup_manifest_tmp" "$manifest_file"
mv -- "$manifest_tmp" "$RUN_ROOT/originals.tsv"
printf '%s\n' "$current_commit" >"$RUN_ROOT/source-commit"
printf 'ACTS_BACKUP_DONE backup=%s run=%s\n' "$BACKUP_ROOT" "$RUN_ROOT"
