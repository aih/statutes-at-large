#!/usr/bin/env bash
# Is this site answering through the edge, and if not, restart its services.
#
#   bash deploy/watchdog.sh                # one probe; cron runs it every minute
#   PROBE_ONLY=1 bash deploy/watchdog.sh   # report, never restart
#
# Probes https://<host>/health and /app/healthz through the edge on this box
# (--resolve to 127.0.0.1), publishes Statutes/SiteUp to CloudWatch before
# acting, and restarts this project's api, frontend and proxy after
# FAIL_THRESHOLD consecutive failures, at most once per RESTART_COOLDOWN and
# never while a deploy holds the lock. It restarts neither the edge nor the
# US Code site's containers. State under ${DATA_ROOT}/watchdog; log at
# ${DATA_ROOT}/logs/watchdog.log.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=deploy/lib.sh
. deploy/lib.sh

DATA_ROOT="$(env_value DATA_ROOT /var/lib/statutes)"
HOST="$(site_host)"
REGION="${AWS_REGION:-us-east-1}"

STATE_DIR="${DATA_ROOT}/watchdog"
STATE_FILE="${STATE_DIR}/consecutive-failures"
LAST_RESTART_FILE="${STATE_DIR}/last-restart"
LOG="${DATA_ROOT}/logs/watchdog.log"

FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"
RESTART_COOLDOWN="${RESTART_COOLDOWN:-600}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-10}"

mkdir -p "$STATE_DIR" "${DATA_ROOT}/logs"

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

if [ -z "$HOST" ]; then
    log "no SITE_ADDRESS in .env — cannot probe"
    exit 1
fi

probe() {
    curl -sS -o /dev/null --max-time "$PROBE_TIMEOUT" \
        --resolve "${HOST}:443:127.0.0.1" \
        -w '%{http_code}' "https://${HOST}$1" 2>/dev/null
}

API_CODE="$(probe /health)"
APP_CODE="$(probe /app/healthz)"
if [ "$API_CODE" = "200" ] && [ "$APP_CODE" = "200" ]; then
    UP=1
else
    UP=0
fi

# The instance id, cached: this runs every minute.
if [ -s "${STATE_DIR}/instance-id" ]; then
    INSTANCE_ID="$(cat "${STATE_DIR}/instance-id")"
else
    INSTANCE_ID="$(imds_instance_id)"
    [ -n "$INSTANCE_ID" ] && echo "$INSTANCE_ID" > "${STATE_DIR}/instance-id"
fi

# Published first, whatever happens below.
if [ -z "$INSTANCE_ID" ]; then
    log "no instance id from IMDS — cannot publish SiteUp=$UP"
elif ! aws cloudwatch put-metric-data --region "$REGION" \
        --namespace Statutes --metric-name SiteUp --value "$UP" --unit None \
        --dimensions "InstanceId=${INSTANCE_ID}" 2>>"$LOG"; then
    log "could not publish SiteUp=$UP"
fi

FAILURES=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
case "$FAILURES" in ''|*[!0-9]*) FAILURES=0 ;; esac

if [ "$UP" = "1" ]; then
    if [ "$FAILURES" -gt 0 ]; then
        log "recovered after $FAILURES failed probes (api=$API_CODE app=$APP_CODE)"
    fi
    echo 0 > "$STATE_FILE"
    exit 0
fi

FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$STATE_FILE"
log "probe failed ($FAILURES/$FAIL_THRESHOLD): api=$API_CODE app=$APP_CODE"

[ -n "${PROBE_ONLY:-}" ] && exit 1
[ "$FAILURES" -lt "$FAIL_THRESHOLD" ] && exit 1

exec 9>"${DATA_ROOT}/deploy.lock"
if ! flock -n 9; then
    log "a deploy holds the lock — not restarting"
    exit 1
fi

NOW=$(date +%s)
LAST=$(cat "$LAST_RESTART_FILE" 2>/dev/null || echo 0)
case "$LAST" in ''|*[!0-9]*) LAST=0 ;; esac
if [ $((NOW - LAST)) -lt "$RESTART_COOLDOWN" ]; then
    log "restarted $((NOW - LAST))s ago — inside the ${RESTART_COOLDOWN}s cooldown, leaving it alone"
    exit 1
fi

echo "$NOW" > "$LAST_RESTART_FILE"
log "restarting api, frontend and proxy after $FAILURES failed probes"
docker compose -f docker-compose.prod.yml restart api frontend proxy >>"$LOG" 2>&1
log "restart returned $?"

sleep 20
API_CODE="$(probe /health)"
APP_CODE="$(probe /app/healthz)"
if [ "$API_CODE" = "200" ] && [ "$APP_CODE" = "200" ]; then
    log "site answering again after restart"
    echo 0 > "$STATE_FILE"
    exit 0
fi

log "still failing after restart: api=$API_CODE app=$APP_CODE"
exit 1
