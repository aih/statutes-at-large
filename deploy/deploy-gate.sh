#!/usr/bin/env bash
# Whether .github/workflows/deploy.yml builds and deploys <sha> (ADR-0026):
#
#   bash deploy/deploy-gate.sh <sha> [health-url]
#
# Prints `deploy=true` or `deploy=false` on stdout, for $GITHUB_OUTPUT, and
# the reason on stderr. `false` only when the commit the site reports on
# /health is <sha> or an ancestor of it, and every path changed between the
# two is documentation: under docs/, or a *.md file outside frontend/.
# Anything else is `true`: /health not answering, `commit` unknown, a commit
# this checkout does not hold, a deployed commit that is not an ancestor.
# Needs the full history (`fetch-depth: 0`).
set -euo pipefail
cd "$(dirname "$0")/.."

NEW="${1:?usage: deploy-gate.sh <sha> [health-url]}"
URL="${2:-https://statutes.linkedlegislation.org/health}"

decide() {
    echo "deploy-gate: $2" >&2
    echo "deploy=$1"
    exit 0
}

DEPLOYED="$(curl -sf --max-time 10 --retry 2 "$URL" | jq -r '.commit // empty' 2>/dev/null || true)"
if [ -z "$DEPLOYED" ] || [ "$DEPLOYED" = "unknown" ]; then
    decide true "$URL did not name a commit"
fi
if ! git cat-file -e "${DEPLOYED}^{commit}" 2>/dev/null; then
    decide true "the deployed commit $DEPLOYED is not in this checkout"
fi
if ! git merge-base --is-ancestor "$DEPLOYED" "$NEW"; then
    decide true "the deployed commit $DEPLOYED is not an ancestor of $NEW"
fi

CHANGED="$(git diff --name-only "$DEPLOYED" "$NEW")"
if [ -z "$CHANGED" ]; then
    decide false "$NEW changes no file since the deployed commit $DEPLOYED"
fi
CODE="$(echo "$CHANGED" | awk '!/^docs\// && !(/\.md$/ && !/^frontend\//)')"
if [ -n "$CODE" ]; then
    decide true "$(echo "$CODE" | wc -l | tr -d ' ') changed path(s) outside docs since $DEPLOYED, first $(echo "$CODE" | head -1)"
fi
decide false "only documentation changed since the deployed commit $DEPLOYED: $(echo "$CHANGED" | wc -l | tr -d ' ') path(s)"
