#!/usr/bin/env bash
# Runs on the box after .github/workflows/deploy.yml has pushed the images,
# over SSM as ec2-user; also the first bring-up and a rollback by hand:
#
#   bash deploy/deploy-on-box.sh <image-tag>
#
# ECR login, the tag pinned into .env as IMAGE_TAG, pull, the migration with
# the new image before it serves, `up -d --wait`, the search index rebuilt if
# this release changed its mapping (`|| echo`: never fatal, ADR-0023), the
# proxy recreated when deploy/Caddyfile changed (after `caddy validate` with
# the proxy's image, before anything else), then robots.txt
# fetched through the edge on this box and asserted, then prune. flock on
# ${DATA_ROOT}/deploy.lock; everything logs to ${DATA_ROOT}/logs/deploy.log.
# It never recreates the edge or the US Code site's containers.
#
# ${DATA_ROOT}/watchdog/deploying holds this run's start time and is removed
# as the script exits: deploy/watchdog.sh reads it and publishes SiteUp=1 for
# a probe that lands in the second the proxy is being recreated.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=deploy/lib.sh
. deploy/lib.sh

TAG="${1:?usage: deploy-on-box.sh <image-tag>}"
COMPOSE="docker compose -f docker-compose.prod.yml"

DATA_ROOT="$(env_value DATA_ROOT /var/lib/statutes)"
ECR_REGISTRY="$(env_value ECR_REGISTRY)"
HOST="$(site_host)"
if [ -z "$ECR_REGISTRY" ]; then
    echo "ECR_REGISTRY not set in .env" >&2
    exit 1
fi
if [ -z "$HOST" ]; then
    echo "SITE_ADDRESS not set in .env" >&2
    exit 1
fi

mkdir -p "$DATA_ROOT/logs"
exec > >(tee -a "$DATA_ROOT/logs/deploy.log") 2>&1

exec 9>"$DATA_ROOT/deploy.lock"
if ! flock -n 9; then
    echo "deploy already running"
    exit 1
fi

mkdir -p "$DATA_ROOT/watchdog"
date +%s > "$DATA_ROOT/watchdog/deploying"
trap 'rm -f "$DATA_ROOT/watchdog/deploying"' EXIT

echo "=== $(date -u +%FT%TZ) deploying $TAG ==="

aws ecr get-login-password --region "${AWS_REGION:-us-east-1}" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Pinned so a later `docker compose up -d` by hand reuses this sha.
if grep -qE '^IMAGE_TAG=' .env 2>/dev/null; then
    sed -i.bak "s/^IMAGE_TAG=.*/IMAGE_TAG=${TAG}/" .env && rm -f .env.bak
else
    echo "IMAGE_TAG=${TAG}" >> .env
fi

# The Grafana Cloud endpoint and header (ADR-0029), from SSM Parameter Store.
bash deploy/otel-env.sh .env

# A Caddyfile that does not parse would leave the proxy down once it is
# recreated, so it is checked with the proxy's own image before anything on
# the box changes (ADR-0030). A failure here leaves the running stack as it was.
echo "=== validating deploy/Caddyfile ==="
docker run --rm \
    -e SITE_ADDRESS="$(env_value SITE_ADDRESS)" \
    -e GATE_HOST="$(env_value GATE_HOST statutes.linkedlegislation.org)" \
    -v "$PWD/deploy/Caddyfile:/etc/caddy/Caddyfile:ro" \
    caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

echo "=== pulling images ==="
$COMPOSE pull api frontend

echo "=== starting the database ==="
$COMPOSE up -d --wait db

echo "=== migrating (new image, before it serves) ==="
$COMPOSE run --rm --no-deps api uv run alembic upgrade head

# A no-op unless the migration or a load moved the data version (ADR-0037).
echo "=== storing the per-Congress counts ==="
$COMPOSE run --rm --no-deps api uv run python -m ingest congress-summaries \
    || echo "congress-summaries failed; the API computes the counts on the first request"

echo "=== bringing the stack up ==="
$COMPOSE up -d --wait

# A failed rebuild leaves the alias where it was, per ADR-0051 of the US Code
# site, which this site's ADR-0023 cites: stale search on a deployed site
# beats rolling back everything else because a reindex timed out.
echo "=== rebuilding the search index if this release changed its mapping ==="
$COMPOSE exec -T api uv run python -m ingest reindex-search --if-changed \
    || echo "reindex-search failed; the live index stays"

# A bind-mounted file's bytes are not a service definition change, and
# `git checkout --force` gives the file a new inode; recreating the container
# is what re-reads deploy/Caddyfile. Only when the file changed (ADR-0030):
# the edge has nothing to dial while the proxy is recreated. The comparison is
# against the file the running container sees, which after the checkout is
# either the old bytes or nothing.
echo "=== recreating the proxy if deploy/Caddyfile changed ==="
REPO_CADDYFILE_SUM="$(sha256sum deploy/Caddyfile | awk '{print $1}')"
LIVE_CADDYFILE_SUM="$($COMPOSE exec -T proxy sha256sum /etc/caddy/Caddyfile 2>/dev/null | awk '{print $1}' || true)"
if [ "$LIVE_CADDYFILE_SUM" = "$REPO_CADDYFILE_SUM" ]; then
    echo "the running proxy has the current Caddyfile; left running"
else
    $COMPOSE up -d --no-deps --force-recreate --wait proxy
fi

# Through the edge, over the real hostname, on this box. The edge is compose
# project `edge` (deploy/edge/up.sh); it needs to be up and to hold the
# certificate for the check to pass.
echo "=== checking robots.txt through the edge ==="
if [ -z "$(docker ps -q --filter label=com.docker.compose.project=edge)" ]; then
    echo "the edge is not running: the stack is up but unreachable from outside."
    echo "Run: bash deploy/edge/up.sh, then re-run this deploy."
    exit 1
fi
curl -sfL --retry 5 --retry-delay 2 --retry-all-errors \
    --resolve "${HOST}:443:127.0.0.1" \
    "https://${HOST}/robots.txt" | grep -qx 'Disallow: /'
echo "robots.txt served as expected"

echo "=== pruning old images ==="
docker image prune -f

echo "=== $(date -u +%FT%TZ) deploy of $TAG complete ==="
