#!/usr/bin/env bash
# The weekly source update on the box (docs/plans/2026-09-08-deployment-plan.md,
# section 6). Every step runs inside the `api` container.
#
#   bash deploy/update-sources.sh               # ask each source; load what changed
#   bash deploy/update-sources.sh --check-only  # record the checks, fetch nothing, load nothing
#   bash deploy/update-sources.sh --force       # reload whether or not anything changed
#
# Steps, each logged with its exit status and time; a failed step is logged
# and the run goes on, and the exit status is 1 when any step failed:
#
#   1  plaw poll --report data/verification
#   2  comps poll --since <the day before the last COMPS check, from /api/v1/status;
#      8 days ago when there is none>
#   3  fetch-statute 1-137 --if-changed, then statute --volumes 1-137 --changed-only
#   4  citations --from-hub --if-changed
#   5  classifications
#   6  pg_dump to s3://${BACKUP_BUCKET}/db/statutes-<date>.dump, only when a
#      step wrote rows: /api/v1/status is read before and after the steps with
#      `checks`, `stale`, `citations.checked_at` and `classifications.last_check`
#      removed (the members every check moves), and a difference means a load.
#   7  /api/v1/status into the log, with `stale` asserted false
#
# --check-only runs the two polls with --limit 0 (the check row is written,
# nothing is fetched) and fetch-statute --if-changed (changed volume files are
# downloaded, not loaded); steps 4 to 6 are skipped. --force runs plaw poll
# --force, comps poll --force, statute without --changed-only, citations
# without --if-changed and classifications --force.
#
# flock on ${DATA_ROOT}/update.lock; the log is ${DATA_ROOT}/logs/update-<date>.log.
# The API is read inside the container (python, no jq on the box), never
# through the public hostname.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=deploy/lib.sh
. deploy/lib.sh

MODE="auto"
case "${1:-}" in
    --check-only) MODE="check-only" ;;
    --force)      MODE="force" ;;
    "")           ;;
    *) echo "usage: $0 [--check-only|--force]" >&2; exit 2 ;;
esac

DATA_ROOT="$(env_value DATA_ROOT /var/lib/statutes)"
BACKUP_BUCKET="$(env_value BACKUP_BUCKET statutes-linkedlegislation)"

mkdir -p "$DATA_ROOT/logs"
LOG_FILE="$DATA_ROOT/logs/update-$(date -u +%F).log"
exec > >(tee -a "$LOG_FILE") 2>&1

exec 9>"$DATA_ROOT/update.lock"
if ! flock -n 9; then
    echo "update already running; this run is a no-op"
    exit 0
fi

COMPOSE=(docker compose -f docker-compose.prod.yml)
INGEST=("${COMPOSE[@]}" exec -T api nice -n 10 uv run python -m ingest)
FAILED=0

# step NAME COMMAND…: run it, log its exit status and time, remember a failure.
step() {
    local name="$1" started status
    shift
    started=$SECONDS
    echo "=== $(date -u +%FT%TZ) [$name] $* ==="
    "$@"
    status=$?
    echo "=== $(date -u +%FT%TZ) [$name] exit $status after $((SECONDS - started))s ==="
    [ "$status" -eq 0 ] || FAILED=1
    return "$status"
}

# /api/v1/status without the members every check moves; equal before and
# after means no step loaded anything.
status_snapshot() {
    "${COMPOSE[@]}" exec -T api python -c '
import json, urllib.request
d = json.load(urllib.request.urlopen("http://localhost:8001/api/v1/status", timeout=30))
d.pop("checks", None)
d.pop("stale", None)
d.get("citations", {}).pop("checked_at", None)
d.get("classifications", {}).pop("last_check", None)
print(json.dumps(d, sort_keys=True))
' 2>/dev/null
}

# The day before the last COMPS check; 8 days ago without one.
comps_since() {
    "${COMPOSE[@]}" exec -T api python -c '
import datetime, json, urllib.request
d = json.load(urllib.request.urlopen("http://localhost:8001/api/v1/status", timeout=30))
check = (d.get("checks") or {}).get("COMPS") or {}
if check.get("checked_at"):
    t = datetime.datetime.fromisoformat(check["checked_at"].replace("Z", "+00:00"))
else:
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
print((t - datetime.timedelta(days=1)).date().isoformat())
' 2>/dev/null
}

# The dump, and each half of the pipe checked: with pipefail alone an `aws`
# that uploaded a truncated stream after pg_dump died still exits 0.
# shellcheck disable=SC2317,SC2329  # invoked through `step`
dump_to_bucket() {
    local key
    key="s3://${BACKUP_BUCKET}/db/statutes-$(date -u +%F).dump"
    "${COMPOSE[@]}" exec -T db pg_dump -U statutes -Fc statutes | aws s3 cp - "$key"
    local st=("${PIPESTATUS[@]}")
    if [ "${st[0]}" -ne 0 ]; then
        echo "pg_dump failed (exit ${st[0]}); nothing trustworthy at $key"
        return 1
    fi
    if [ "${st[1]}" -ne 0 ]; then
        echo "aws s3 cp failed (exit ${st[1]})"
        return 1
    fi
    echo "dumped to $key"
}

# /api/v1/status into the log; exit 1 when `stale` is not false.
# shellcheck disable=SC2317,SC2329  # invoked through `step`
status_report() {
    "${COMPOSE[@]}" exec -T api python -c '
import json, sys, urllib.request
d = json.load(urllib.request.urlopen("http://localhost:8001/api/v1/status", timeout=30))
print(json.dumps(d, indent=2))
sys.exit(0 if d.get("stale") is False else 1)
'
}

echo "=== $(date -u +%FT%TZ) source update starting (mode: ${MODE}) ==="

BEFORE="$(status_snapshot)"
if [ -z "$BEFORE" ]; then
    echo "could not read /api/v1/status before the steps; a dump will be taken if the steps succeed"
fi

SINCE="$(comps_since)"
if [ -z "$SINCE" ]; then
    SINCE="$(date -u -d '8 days ago' +%F 2>/dev/null || date -u -v-8d +%F)"
    echo "could not read the last COMPS check; using --since $SINCE"
fi

case "$MODE" in
    check-only)
        step plaw "${INGEST[@]}" plaw poll --limit 0
        step comps "${INGEST[@]}" comps poll --limit 0 --since "$SINCE"
        step fetch-statute "${INGEST[@]}" fetch-statute 1-137 --if-changed
        echo "check-only: nothing loaded, no dump"
        ;;
    force)
        step plaw "${INGEST[@]}" plaw poll --force --report data/verification
        step comps "${INGEST[@]}" comps poll --force --since "$SINCE"
        step fetch-statute "${INGEST[@]}" fetch-statute 1-137 --if-changed
        step statute "${INGEST[@]}" statute --volumes 1-137 --report data/verification
        step citations "${INGEST[@]}" citations --from-hub --report data/verification
        step classifications "${INGEST[@]}" classifications --force --report data/verification
        ;;
    auto)
        step plaw "${INGEST[@]}" plaw poll --report data/verification
        step comps "${INGEST[@]}" comps poll --since "$SINCE"
        step fetch-statute "${INGEST[@]}" fetch-statute 1-137 --if-changed
        step statute "${INGEST[@]}" statute --volumes 1-137 --changed-only --report data/verification
        step citations "${INGEST[@]}" citations --from-hub --if-changed --report data/verification
        step classifications "${INGEST[@]}" classifications --report data/verification
        ;;
esac

if [ "$MODE" != "check-only" ]; then
    AFTER="$(status_snapshot)"
    if [ -z "$BEFORE" ] || [ -z "$AFTER" ] || [ "$BEFORE" != "$AFTER" ]; then
        echo "rows were written (or the status could not be compared): dumping"
        step dump dump_to_bucket
    else
        echo "nothing loaded — no dump; the last one is still current"
    fi
fi

step status status_report

echo "=== $(date -u +%FT%TZ) source update complete (mode: ${MODE}, failed steps: ${FAILED}) ==="
exit "$FAILED"
