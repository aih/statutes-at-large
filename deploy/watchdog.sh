#!/usr/bin/env bash
# Is this site answering through the edge, and if not, restart what failed.
#
#   bash deploy/watchdog.sh                # one probe; cron runs it every minute
#   PROBE_ONLY=1 bash deploy/watchdog.sh   # report, never restart
#
# Probes https://<host>/health and /app/healthz through the edge on this box
# (--resolve to 127.0.0.1) and publishes four metrics in the namespace
# Statutes before acting: SiteUp (both surfaces answered 200), ApiUp, AppUp,
# and EdgeUp (0 when the connection to 443 is refused). Only SiteUp is
# alarmed; the other three say which half failed (ADR-0024).
#
# It restarts the services whose surface failed — api, frontend, or both with
# the proxy — after FAIL_THRESHOLD consecutive failures, at most once per
# RESTART_COOLDOWN, never while a deploy holds the lock, and never when the
# edge is what is refusing connections (ADR-0017 decision 9). It restarts
# neither the edge nor the US Code site's containers.
#
# While deploy-on-box.sh's marker file is fresh, a failed probe publishes
# SiteUp=1 and is not counted: a deploy recreates the proxy and one probe in
# that second sees a 502. ApiUp, AppUp and EdgeUp still carry what the probe
# saw. State under ${DATA_ROOT}/watchdog; log at
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
DEPLOY_MARK="${STATE_DIR}/deploying"
LOG="${DATA_ROOT}/logs/watchdog.log"

FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"
RESTART_COOLDOWN="${RESTART_COOLDOWN:-600}"
PROBE_TIMEOUT="${PROBE_TIMEOUT:-10}"
# The longest a deploy's marker suppresses a failure. A deploy is 40 to 60 s
# and removes the marker as it exits; a run killed outright leaves it, and
# after this many seconds it counts for nothing.
DEPLOY_WINDOW="${DEPLOY_WINDOW:-900}"

mkdir -p "$STATE_DIR" "${DATA_ROOT}/logs"

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

if [ -z "$HOST" ]; then
    log "no SITE_ADDRESS in .env — cannot probe"
    exit 1
fi

# `<http code> <curl exit status>`. curl's 7 is a refused connection, which on
# 443 is the edge and not this site.
probe() {
    local code status
    code="$(curl -sS -o /dev/null --max-time "$PROBE_TIMEOUT" \
        --resolve "${HOST}:443:127.0.0.1" \
        -w '%{http_code}' "https://${HOST}$1" 2>/dev/null)"
    status=$?
    printf '%s %s' "${code:-000}" "$status"
}

read -r API_CODE API_STATUS <<<"$(probe /health)"
read -r APP_CODE APP_STATUS <<<"$(probe /app/healthz)"

API_UP=0; [ "$API_CODE" = "200" ] && API_UP=1
APP_UP=0; [ "$APP_CODE" = "200" ] && APP_UP=1
EDGE_UP=1; [ "$API_STATUS" = "7" ] && [ "$APP_STATUS" = "7" ] && EDGE_UP=0
UP=0; [ "$API_UP" = "1" ] && [ "$APP_UP" = "1" ] && UP=1

# A deploy is running: the site is allowed to be unavailable for a second
# while the proxy is recreated.
DEPLOYING=0
if [ -s "$DEPLOY_MARK" ]; then
    STARTED="$(cat "$DEPLOY_MARK" 2>/dev/null || echo 0)"
    case "$STARTED" in ''|*[!0-9]*) STARTED=0 ;; esac
    [ $(( $(date +%s) - STARTED )) -lt "$DEPLOY_WINDOW" ] && DEPLOYING=1
fi
if [ "$UP" = "0" ] && [ "$DEPLOYING" = "1" ]; then
    log "a deploy is running: probe failed (api=$API_CODE app=$APP_CODE), publishing SiteUp=1"
    UP=1
fi

# The instance id, cached: this runs every minute.
if [ -s "${STATE_DIR}/instance-id" ]; then
    INSTANCE_ID="$(cat "${STATE_DIR}/instance-id")"
else
    INSTANCE_ID="$(imds_instance_id)"
    [ -n "$INSTANCE_ID" ] && echo "$INSTANCE_ID" > "${STATE_DIR}/instance-id"
fi

# Published first, whatever happens below. One call carries all four.
metric() {
    printf '{"MetricName":"%s","Value":%s,"Unit":"None","Dimensions":[{"Name":"InstanceId","Value":"%s"}]}' \
        "$1" "$2" "$INSTANCE_ID"
}
if [ -z "$INSTANCE_ID" ]; then
    log "no instance id from IMDS — cannot publish SiteUp=$UP"
elif ! aws cloudwatch put-metric-data --region "$REGION" --namespace Statutes \
        --metric-data "[$(metric SiteUp "$UP"),$(metric ApiUp "$API_UP"),$(metric AppUp "$APP_UP"),$(metric EdgeUp "$EDGE_UP")]" \
        2>>"$LOG"; then
    log "could not publish SiteUp=$UP"
fi

FAILURES=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
case "$FAILURES" in ''|*[!0-9]*) FAILURES=0 ;; esac

if [ "$UP" = "1" ]; then
    if [ "$FAILURES" -gt 0 ] && [ "$DEPLOYING" = "0" ]; then
        log "recovered after $FAILURES failed probes (api=$API_CODE app=$APP_CODE)"
    fi
    echo 0 > "$STATE_FILE"
    exit 0
fi

FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$STATE_FILE"
log "probe failed ($FAILURES/$FAIL_THRESHOLD): api=$API_CODE app=$APP_CODE"

if [ "$EDGE_UP" = "0" ]; then
    log "nothing is listening on 443: the edge is down, and this site's services are not what to restart"
    exit 1
fi

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

# What failed, and the proxy only when both surfaces did: it is the hop they
# share, and restarting it while one half is answering takes that half down
# too. `docker compose restart` keeps the container, and so its `edge`
# attachment and alias.
SERVICES=""
[ "$API_UP" = "0" ] && SERVICES="api"
[ "$APP_UP" = "0" ] && SERVICES="${SERVICES:+$SERVICES }frontend"
[ "$API_UP" = "0" ] && [ "$APP_UP" = "0" ] && SERVICES="$SERVICES proxy"

echo "$NOW" > "$LAST_RESTART_FILE"
log "restarting $SERVICES after $FAILURES failed probes"
# shellcheck disable=SC2086
docker compose -f docker-compose.prod.yml restart $SERVICES >>"$LOG" 2>&1
log "restart returned $?"

sleep 20
read -r API_CODE _ <<<"$(probe /health)"
read -r APP_CODE _ <<<"$(probe /app/healthz)"
if [ "$API_CODE" = "200" ] && [ "$APP_CODE" = "200" ]; then
    log "site answering again after restart"
    echo 0 > "$STATE_FILE"
    exit 0
fi

log "still failing after restart: api=$API_CODE app=$APP_CODE"
exit 1
