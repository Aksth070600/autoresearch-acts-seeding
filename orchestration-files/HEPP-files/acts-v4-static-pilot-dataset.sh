#!/usr/bin/env bash
# Generate, fully qualify, and atomically publish the canonical LZ4 payload.
set -euo pipefail
MODULE_DIR="${1:?static-v4 module is required}"
PILOT_ROOT="${2:?task-owned pilot root is required}"
GEOMETRY_DIR="${3:?geometry directory is required}"
IDENTITY_DIR="${4:?private build identity directory is required}"
CANONICAL_ROOT="${5:?canonical publication root is required}"
ACTS_SOURCE="${ACTS_SOURCE:?private ACTS source is required}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:?private ACTS build is required}"
export ACTS_SOURCE ACTS_BUILD_DIR
GENESIS=5ed3b47329ceda4edaab48b1efc3c5635f361a30
PROTOCOL_ONE=acts-seeding-v4-owned-static-test-pilot-one
PROTOCOL_FIFTY=acts-seeding-v4-owned-static-test-pilot-fifty
DATASET_ONE=acts-v4-owned-static-pilot-one
DATASET_FIFTY=acts-v4-owned-static-pilot-fifty

if [[ -e "$PILOT_ROOT/qualification" ]]; then
  echo "error: pilot qualification workspace already exists" >&2
  exit 2
fi
mkdir -p -- "$PILOT_ROOT/qualification"
lock_path="$PILOT_ROOT/.campaign.lock"
exec 9>"$lock_path"
flock 9

bash "$(dirname -- "$MODULE_DIR")/HEPP-files/acts-v4-static-roundtrip.sh" \
  "$MODULE_DIR" "$PILOT_ROOT/qualification/one" "$GEOMETRY_DIR" "$IDENTITY_DIR" \
  "$PROTOCOL_ONE" "$DATASET_ONE" 1 lz4 4 "$GENESIS"

bash "$(dirname -- "$MODULE_DIR")/HEPP-files/acts-v4-static-roundtrip.sh" \
  "$MODULE_DIR" "$PILOT_ROOT/qualification/fifty" "$GEOMETRY_DIR" "$IDENTITY_DIR" \
  "$PROTOCOL_FIFTY" "$DATASET_FIFTY" 50 lz4 4 "$GENESIS"

bash "$(dirname -- "$MODULE_DIR")/HEPP-files/acts-v4-static-negative-qualification.sh" \
  "$MODULE_DIR" "$PILOT_ROOT/qualification/one/dataset" \
  "$PILOT_ROOT/qualification/negative" "$GEOMETRY_DIR" "$IDENTITY_DIR" \
  "$PROTOCOL_ONE" "$DATASET_ONE" \
  | tee "$PILOT_ROOT/qualification/negative.log"

bash "$(dirname -- "$MODULE_DIR")/HEPP-files/acts-v4-static-timed.sh" \
  "$MODULE_DIR" "$PILOT_ROOT/qualification/fifty/dataset" \
  "$PILOT_ROOT/qualification/latency" "$GEOMETRY_DIR" "$IDENTITY_DIR" \
  "$PROTOCOL_FIFTY" "$DATASET_FIFTY"

PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/build_qualification_evidence.py" \
  --dataset "$PILOT_ROOT/qualification/fifty/dataset" \
  --one-event-equality "$PILOT_ROOT/qualification/one/exact-equality.json" \
  --fifty-event-equality "$PILOT_ROOT/qualification/fifty/exact-equality.json" \
  --negative-log "$PILOT_ROOT/qualification/negative.log" \
  --latency-result "$PILOT_ROOT/qualification/latency/result.json" \
  --output "$PILOT_ROOT/qualification/evidence.json"

if [[ ! -e "$CANONICAL_ROOT" ]]; then
  mkdir -m 0700 -- "$CANONICAL_ROOT"
fi
if [[ ! -d "$CANONICAL_ROOT" || -L "$CANONICAL_ROOT" || ! -O "$CANONICAL_ROOT" ]]; then
  echo "error: canonical root must be a user-owned regular directory" >&2
  exit 2
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$MODULE_DIR/promote_dataset.py" \
  --qualification-dataset "$PILOT_ROOT/qualification/fifty/dataset" \
  --canonical-root "$CANONICAL_ROOT" \
  --qualification-evidence "$PILOT_ROOT/qualification/evidence.json" \
  --publication-record "$PILOT_ROOT/qualification/publication.json"
printf 'canonical_publication_record=%s\n' "$PILOT_ROOT/qualification/publication.json"
