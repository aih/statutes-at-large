#!/usr/bin/env bash
# The `edge` network and the edge Caddy (deploy/edge/docker-compose.yml).
#
#   bash deploy/edge/up.sh
#
# Creates the network with the subnet EDGE_SUBNET (default 10.83.0.0/24, the
# range the inner Caddyfiles trust) when it is absent, and refuses to go on
# when a network named `edge` exists with another subnet. Then brings the
# Caddy up and waits for it. Idempotent; prints what it reused.
#
# The site addresses, ports and DATA_ROOT come from the environment
# (docker-compose.yml here lists them); the production defaults need none.
set -euo pipefail
cd "$(dirname "$0")"

NETWORK="edge"
EDGE_SUBNET="${EDGE_SUBNET:-10.83.0.0/24}"

echo "==> network $NETWORK ($EDGE_SUBNET)"
if docker network inspect "$NETWORK" >/dev/null 2>&1; then
    existing="$(docker network inspect "$NETWORK" \
        --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}')"
    if [ "$existing" != "$EDGE_SUBNET" ]; then
        echo "network $NETWORK exists with subnet '${existing}', not $EDGE_SUBNET (EDGE_SUBNET)." >&2
        echo "The inner Caddyfiles trust the subnet the edge uses (deploy/Caddyfile:" >&2
        echo "trusted_proxies). Remove the network, or set EDGE_SUBNET to '${existing}'" >&2
        echo "and check the Caddyfiles; not using it as is." >&2
        exit 1
    fi
    echo "    reusing $NETWORK ($existing)"
else
    docker network create --subnet "$EDGE_SUBNET" "$NETWORK" >/dev/null
    echo "    created $NETWORK"
fi

echo "==> edge caddy"
docker compose -p edge -f docker-compose.yml up -d --wait
docker compose -p edge -f docker-compose.yml ps --format '    {{.Name}}  {{.Status}}  {{.Ports}}'
