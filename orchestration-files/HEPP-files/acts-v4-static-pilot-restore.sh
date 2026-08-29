#!/usr/bin/env bash
# Restore the final candidate slot exactly to immutable canonical Genesis.
set -euo pipefail
MODULE_DIR="${1:?static-v4 module is required}"
TEMPLATE="${2:?immutable Genesis template is required}"
SLOT="${3:?task-owned candidate slot is required}"
GENESIS_OPTIMIZATION="${4:?canonical Genesis optimization tree is required}"
if [[ ! -d "$TEMPLATE/source" || ! -d "$TEMPLATE/build" || ! -d "$TEMPLATE/identities" ]]; then
  echo "error: immutable Genesis template is incomplete" >&2
  exit 2
fi
lock_path="$(dirname -- "$TEMPLATE")/.campaign.lock"
exec 9>"$lock_path"
flock 9
rm -rf -- "$SLOT"
cp -a --reflink=always -- "$TEMPLATE" "$SLOT"
ACTS_SOURCE="$SLOT/source" ACTS_BUILD_DIR="$SLOT/build" \
PYTHONDONTWRITEBYTECODE=1 python3 - "$MODULE_DIR" "$SLOT" "$GENESIS_OPTIMIZATION" <<'PY'
import sys
from pathlib import Path
module, slot, genesis = map(Path, sys.argv[1:])
sys.path.insert(0, str(module))
from identity import validate_private_build
validate_private_build(slot / "source", slot / "build", slot / "identities")
for path in sorted(genesis.rglob("*")):
    if path.is_file():
        relative = path.relative_to(genesis)
        if (slot / "source" / relative).read_bytes() != path.read_bytes():
            raise SystemExit(f"final Genesis source mismatch: {relative}")
print("final_genesis_source_identity=passed")
PY
dry_run="$(ninja -C "$SLOT/build" -n ActsPythonBindings)"
printf '%s\n' "$dry_run"
if [[ "$dry_run" != *"no work to do"* ]]; then
  echo "error: final Genesis binary closure has pending work" >&2
  exit 1
fi
printf 'final_genesis_restoration=passed source_binary_consistent=yes slot=%s\n' "$SLOT"
