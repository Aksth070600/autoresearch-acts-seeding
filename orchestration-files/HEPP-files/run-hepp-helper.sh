#!/usr/bin/env bash
set -euo pipefail

HELPER="${1:?helper name is required}"
RUN_ID="${2:?run id is required}"
shift 2

HEPP_HOST="${HEPP_HOST:-thomaaks@hepp02.hpc.uio.no}"
HEPP_STORAGE="${HEPP_STORAGE:-/storage/thomaaks}"
HEPP_TMUX_TARGET="${HEPP_TMUX_TARGET:-acts-hepp02:0}"
ACTS_SOURCE="${ACTS_SOURCE:-/storage/thomaaks/acts-v46.5.0}"
ACTS_BUILD_DIR="${ACTS_BUILD_DIR:-$ACTS_SOURCE/build}"
HEPP_RUN_TIMEOUT="${HEPP_RUN_TIMEOUT:-1800}"

if [[ ! "$HELPER" =~ ^[A-Za-z0-9._-]+\.sh$ ]]; then
  echo "error: unsafe helper name: $HELPER" >&2
  exit 2
fi
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "error: unsafe run id: $RUN_ID" >&2
  exit 2
fi

start_marker="ACTS_HELPER_START[$RUN_ID]"
end_marker="ACTS_HELPER_DONE[$RUN_ID]"
remote_command="printf '%s\\n' '$start_marker'; cd $(printf '%q' "$HEPP_STORAGE") && ACTS_SOURCE=$(printf '%q' "$ACTS_SOURCE") ACTS_BUILD_DIR=$(printf '%q' "$ACTS_BUILD_DIR") bash $(printf '%q' "HEPP-files/$HELPER")"
for argument in "$@"; do
  remote_command+=" $(printf '%q' "$argument")"
done
remote_command+="; rc=\$?; printf '%s%s%s rc=%s\\n' 'ACTS_HELPER_DONE[' '$RUN_ID' ']' \"\$rc\""

ssh "$HEPP_HOST" "tmux has-session -t '$HEPP_TMUX_TARGET' && tmux send-keys -t '$HEPP_TMUX_TARGET' $(printf '%q' "$remote_command") C-m"

deadline=$(( $(date +%s) + HEPP_RUN_TIMEOUT ))
captured=''
done=0
while (( $(date +%s) < deadline )); do
  captured="$(ssh "$HEPP_HOST" "tmux capture-pane -p -J -t '$HEPP_TMUX_TARGET' -S -" 2>/dev/null || true)"
  if printf '%s\n' "$captured" | grep -Fq "$end_marker"; then
    done=1
    break
  fi
  sleep 2
done

if (( done != 1 )); then
  echo "error: helper timed out: $HELPER" >&2
  exit 1
fi

printf '%s\n' "$captured" | awk -v start="$start_marker" -v end="$end_marker" '
  index($0, start) == 1 { inside=1; next }
  index($0, end) == 1 { exit }
  inside { print }
'
remote_rc="$(printf '%s\n' "$captured" | awk -v marker="$end_marker" 'index($0, marker) == 1 { sub(/^.* rc=/, ""); print; exit }')"
if [[ -z "$remote_rc" ]]; then
  echo "error: helper completion status was missing: $HELPER" >&2
  exit 1
fi
printf 'ACTS_HELPER_RESULT[%s] rc=%s\n' "$RUN_ID" "$remote_rc"
exit "$remote_rc"
