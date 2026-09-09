#!/usr/bin/env bash
# The box's schedule for this site, written whole to /etc/cron.d/statutes:
#
#   sudo bash deploy/install-crons.sh
#
# Three jobs: the weekly source update on Thursdays (the backstop of
# .github/workflows/update-sources.yml, which runs Mondays; the two schedules
# fail independently), the watchdog every minute, and a weekly image prune.
# bootstrap-box.sh calls it; re-run it after an edit here.
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/ec2-user/statutes-at-large}"
DATA_ROOT="${DATA_ROOT:-/var/lib/statutes}"
CRON_FILE=/etc/cron.d/statutes

if [ "$(id -u)" -ne 0 ]; then
    echo "run this as root — it writes $CRON_FILE" >&2
    exit 1
fi

cat > "$CRON_FILE" <<EOF
# Managed by deploy/install-crons.sh in statutes-at-large — edit there, not here.
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin

# Thursdays 06:41 UTC: the weekly source update (deploy/update-sources.sh).
41 6 * * 4 root cd ${REPO_DIR} && sudo -u ec2-user bash deploy/update-sources.sh >> ${DATA_ROOT}/logs/cron-update.log 2>&1

# Every minute: the watchdog. It writes its own log and takes the deploy lock
# before restarting anything.
* * * * * root cd ${REPO_DIR} && sudo -u ec2-user bash deploy/watchdog.sh >/dev/null 2>&1

# Sundays 05:23 UTC: drop dangling images left by deploys.
23 5 * * 0 root docker image prune -f >> ${DATA_ROOT}/logs/prune.log 2>&1
EOF

chmod 0644 "$CRON_FILE"
mkdir -p "${DATA_ROOT}/logs"

echo "wrote $CRON_FILE:"
sed 's/^/    /' "$CRON_FILE"
echo
echo "crond picks up /etc/cron.d changes without a restart; confirm with:"
echo "  systemctl status crond"
