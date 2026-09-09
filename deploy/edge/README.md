# The edge

One Caddy in front of both sites on the box (`docs/plans/2026-09-08-deployment-plan.md`,
section 1). It terminates TLS for `uscode.linkedlegislation.org` and
`statutes.linkedlegislation.org` and hands each to that site's own Caddy over
the external Docker network `edge` (subnet `10.83.0.0/24`), under the aliases
`uscode-proxy` and `statutes-proxy`. Each inner Caddyfile trusts that subnet
and no other, so the client address the edge forwards survives the inner hop
and a peer on the dev stack cannot forge one.

Files:

- `docker-compose.yml` — compose project `edge`: the Caddy, its ports, its
  certificate store at `${DATA_ROOT}/edge-caddy`.
- `Caddyfile` — the two site blocks; addresses from `USCODE_SITE_ADDRESS` and
  `STATUTES_SITE_ADDRESS`, production hostnames by default.
- `up.sh` — creates the network with the subnet when absent, refuses a
  network named `edge` with another subnet, brings the Caddy up. Idempotent.
  `--network-only` stops after the network.

On the box, in this order:

```
bash deploy/edge/up.sh --network-only   # before the US Code site's deploy: its compose file needs the network
bash deploy/edge/up.sh                  # after that deploy, before deploy/deploy-on-box.sh here
```

## The rehearsal on a workstation

Both dev stacks running (this repository's on :8010, the US Code site's on
:8000). Plain HTTP on :8020; `EDGE_HTTPS_PORT` is bound but nothing listens
on it, so pick a free port.

```
export EDGE_HTTP_PORT=8020 EDGE_HTTPS_PORT=8443 \
       USCODE_SITE_ADDRESS=http://uscode.localhost:8020 \
       STATUTES_SITE_ADDRESS=http://statutes.localhost:8020 \
       DATA_ROOT=/tmp/statutes-edge-rehearsal
mkdir -p "$DATA_ROOT"
bash deploy/edge/up.sh

# This repository's dev proxy joins the network under its alias.
docker compose -f docker-compose.yml -f docker-compose.edge.yml up -d --no-deps --force-recreate proxy

# The US Code dev proxy joins at runtime; nothing changes in that repository.
docker network connect --alias uscode-proxy edge uscode-redesign-proxy-1
```

Checks (`*.localhost` resolves for curl on macOS and Linux; otherwise add
`--resolve statutes.localhost:8020:127.0.0.1`):

```
curl -s http://statutes.localhost:8020/health
curl -s http://statutes.localhost:8020/app/healthz
curl -s http://statutes.localhost:8020/robots.txt
curl -s -o /dev/null -w '%{http_code}\n' http://statutes.localhost:8020/app/us/pl/81/740/s3
curl -s http://uscode.localhost:8020/health
curl -s http://uscode.localhost:8020/robots.txt

# A forged address does not survive: the inner proxy's log shows client_ip as
# the address the edge forwarded, and the edge's log shows client_ip equal to
# remote_ip.
curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.9' 'http://statutes.localhost:8020/health?probe=xff'
docker compose logs proxy | grep probe=xff
docker compose -p edge -f deploy/edge/docker-compose.yml logs | grep probe=xff

# The cite bucket is per client address: 75 requests drain it, the next one
# is 429 whatever header it carries, and another address still gets 200.
for i in $(seq 1 75); do curl -s -o /dev/null -w '%{http_code}\n' 'http://statutes.localhost:8020/api/v1/cite?q=64%20Stat.%20563'; done | sort | uniq -c
curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Forwarded-For: 198.51.100.7' 'http://statutes.localhost:8020/api/v1/cite?q=64%20Stat.%20563'
docker compose exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://proxy:8000/api/v1/cite?q=64%20Stat.%20563').status)"
```

Taking it down:

```
docker compose -p edge -f deploy/edge/docker-compose.yml down
docker network disconnect edge uscode-redesign-proxy-1
docker compose up -d --no-deps --force-recreate proxy    # the dev proxy from the dev file alone
docker network rm edge                                    # optional; up.sh recreates it
```
