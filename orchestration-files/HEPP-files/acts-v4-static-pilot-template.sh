#!/usr/bin/env bash
# Freeze the complete prebuilt Genesis slot as an immutable reflink template.
set -euo pipefail
MODULE_DIR="${1:?static-v4 module is required}"
SLOT="${2:?prebuilt Genesis slot is required}"
TEMPLATE="${3:?new immutable template path is required}"
GENESIS_OPTIMIZATION="${4:?canonical Genesis optimization tree is required}"
if [[ -e "$TEMPLATE" || ! -d "$SLOT/source" || ! -d "$SLOT/build" || ! -d "$SLOT/deps" ]]; then
  echo "error: template exists or Genesis slot is incomplete" >&2
  exit 2
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/apply_overlay.py" verify --source "$SLOT/source" >/dev/null
python3 - "$SLOT/source" "$GENESIS_OPTIMIZATION" <<'PY'
import sys
from pathlib import Path
source, genesis = map(Path, sys.argv[1:])
for path in sorted(genesis.rglob("*")):
    if path.is_file():
        relative = path.relative_to(genesis)
        if not (source / relative).is_file() or (source / relative).read_bytes() != path.read_bytes():
            raise SystemExit(f"Genesis source mismatch: {relative}")
print("canonical_genesis_source=passed")
PY
dry_run="$(ninja -C "$SLOT/build" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: Genesis build has pending work" >&2
  exit 1
fi
mkdir -- "$TEMPLATE"
for component in source build deps identities; do
  cp -a --reflink=always -- "$SLOT/$component" "$TEMPLATE/$component"
done
chmod -R a-w -- "$TEMPLATE"
if find "$TEMPLATE" -type f -perm /222 -print -quit | grep -q .; then
  echo "error: immutable template retained writable files" >&2
  exit 1
fi
printf 'immutable_genesis_template=%s\n' "$TEMPLATE"
