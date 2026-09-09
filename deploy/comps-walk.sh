#!/usr/bin/env bash
# The first walk of the COMPS collection: `make comps-walk` once an hour until
# a run loads nothing.
#
#   sudo systemd-run --unit statutes-comps-walk --uid ec2-user \
#       --working-directory /home/ec2-user/statutes-at-large bash deploy/comps-walk.sh
#   systemctl is-active statutes-comps-walk      # inactive once the walk is over
#   tail -f /var/lib/statutes/logs/comps-walk.log
#
# Each run fetches at most 400 packages (two API calls each under GovInfo's
# 1,000 calls an hour) and skips packages already current without a call, so
# the runs advance through the collection. The walk ends on a run whose
# summary line says `0 new, 0 new versions` (ingest.comps.NOTHING_NEW): a
# package that fails to load counts as fetched and fails again on the next
# run, so a rule of "0 fetched" would never fire while any package fails.
# MAX_RUNS bounds the walk if the API keeps failing. Every run is logged whole
# under ${DATA_ROOT}/logs/comps-walk.log.
#
#   WALK_CMD    the command of one run; default `make comps-walk`
#   INTERVAL    seconds between runs; default 3600
#   MAX_RUNS    default 48
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=deploy/lib.sh
. deploy/lib.sh

DATA_ROOT="$(env_value DATA_ROOT /var/lib/statutes)"
LOG="${LOG:-${DATA_ROOT}/logs/comps-walk.log}"
WALK_CMD="${WALK_CMD:-make comps-walk}"
INTERVAL="${INTERVAL:-3600}"
MAX_RUNS="${MAX_RUNS:-48}"
NOTHING_NEW=", 0 new, 0 new versions,"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

run=0
while [ "$run" -lt "$MAX_RUNS" ]; do
    run=$((run + 1))
    echo "=== $(date -u +%FT%TZ) run $run ==="
    echo "$WALK_CMD"
    output="$($WALK_CMD 2>&1)"
    status=$?
    printf '%s\n' "$output"
    echo "=== $(date -u +%FT%TZ) run $run exit $status ==="
    if printf '%s\n' "$output" | grep -qF "$NOTHING_NEW"; then
        echo "=== $(date -u +%FT%TZ) walk complete after $run run(s) ==="
        exit 0
    fi
    sleep "$INTERVAL"
done
echo "=== $(date -u +%FT%TZ) walk stopped after $MAX_RUNS runs without a run that loaded nothing ==="
exit 1
