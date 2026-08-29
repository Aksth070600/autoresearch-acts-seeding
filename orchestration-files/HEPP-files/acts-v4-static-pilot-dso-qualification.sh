#!/usr/bin/env bash
# Qualify complete loaded-ACTS-object closure inspection before revision 2.
set -euo pipefail
MODULE_DIR="${1:?static-v4 module is required}"
BUILD_DIR="${2:?validated private build is required}"
OUTPUT="${3:?new qualification evidence path is required}"
ACTS_LCG_SETUP="${ACTS_LCG_SETUP:-/cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc13-opt/setup.sh}"
if [[ -e "$OUTPUT" || ! -f "$ACTS_LCG_SETUP" || ! -f "$BUILD_DIR/python/setup.sh" ]]; then
  echo "error: output exists or pinned environment is incomplete" >&2
  exit 2
fi
unset CC CXX FC
set +e +u
# shellcheck disable=SC1090
source "$ACTS_LCG_SETUP"
setup_rc=$?
set -e
if (( setup_rc != 0 )); then
  echo "error: LCG setup failed: $setup_rc" >&2
  exit 1
fi
# shellcheck disable=SC1090,SC1091
source "$BUILD_DIR/python/setup.sh"
set -u
PYTHONDONTWRITEBYTECODE=1 python3 - "$MODULE_DIR" "$BUILD_DIR" "$OUTPUT" <<'PY'
import hashlib
import json
import sys
import tempfile
from pathlib import Path

module, build, output = map(Path, sys.argv[1:])
sys.path.insert(0, str(module))
import acts
import acts.examples
import acts.examples.root
from loaded_dsos import loaded_acts_dsos
from schema import ManifestError, canonical_json_bytes, sha256_bytes

closure = loaded_acts_dsos(build)
if "lib64/libActsCore.so" not in closure:
    raise SystemExit("qualified closure lacks ActsCore")
if not any("PythonBindings" in path for path in closure):
    raise SystemExit("qualified closure lacks an ACTS Python binding")
with tempfile.TemporaryDirectory(prefix="acts-v4-dso-negative-") as temporary:
    root = Path(temporary)
    outside = root / "libActsOutside.so"
    outside.write_bytes(b"outside")
    private_core = build / "lib64/libActsCore.so"
    maps = root / "maps"
    maps.write_text(
        "7f000000-7f001000 r-xp 0 00:00 0 " + str(private_core) + "\n"
        "7f001000-7f002000 r-xp 0 00:00 0 " + str(outside) + "\n",
        encoding="utf-8",
    )
    try:
        loaded_acts_dsos(build, maps_path=maps)
    except ManifestError as error:
        if "outside validated private build" not in str(error):
            raise
    else:
        raise SystemExit("external ACTS object was not rejected")
value = {
    "schema": "acts-v4-owned-static-loaded-dso-qualification-v1",
    "protocol_revision": 2,
    "acts_version": list(acts.__version__),
    "inspection": "/proc/self/maps",
    "complete_private_closure_passed": True,
    "external_acts_object_rejection_passed": True,
    "loaded_acts_object_count": len(closure),
    "loaded_acts_dsos": closure,
    "loaded_dso_manifest_sha256": sha256_bytes(canonical_json_bytes(closure)),
}
value["qualification_sha256"] = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(canonical_json_bytes(value))
print(f"loaded_acts_dso_qualification={output}")
print(f"loaded_acts_object_count={len(closure)}")
PY
chmod 0440 "$OUTPUT"
