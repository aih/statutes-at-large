# The edge

One Caddy in front of the sites on the box (`docs/plans/2026-09-08-deployment-plan.md`,
section 1). It terminates TLS for `uscode.linkedlegislation.org`,
`statutes.linkedlegislation.org`, `reintro.linkedlegislation.org` and
`codification.linkedlegislation.org` and hands each to that site's own Caddy
over the external Docker network `edge` (subnet `10.83.0.0/24`), under the
aliases `uscode-proxy`, `statutes-proxy`, `reintro-proxy` and
`codification-proxy`. The third is the reintroductions-us compose project; its
`docs/deploy.md` has its setup. The fourth is one container run by
aih/codification-bills `deploy/deploy-on-box.sh`; that repository's
`deploy/README.md` has its setup. Each inner Caddyfile trusts that subnet
and no other, so the client address the edge forwards survives the inner hop
and a peer on the dev stack cannot forge one.

Files:

- `docker-compose.yml` — compose project `edge`: the Caddy, its ports, its
  certificate store at `${DATA_ROOT}/edge-caddy`.
- `Caddyfile` — Cloudflare's ranges and the four site blocks; addresses from `USCODE_SITE_ADDRESS`,
  `STATUTES_SITE_ADDRESS`, `REINTRO_SITE_ADDRESS` and
  `CODIFICATION_SITE_ADDRESS`, production hostnames by default.
- `up.sh` — creates the network with the subnet when absent, refuses a
  network named `edge` with another subnet, brings the Caddy up. Idempotent.
  `--network-only` stops after the network.

On the box, in this order:

```
bash deploy/edge/up.sh --network-only   # before the US Code site's deploy: its compose file needs the network
bash deploy/edge/up.sh                  # after that deploy, before deploy/deploy-on-box.sh here
```

After a change to `Caddyfile`, recreate the Caddy. The file is a single-file
bind mount, so a `caddy reload` or `up -d` reads the file as it was before the
checkout; both sites are unreachable for the few seconds of the recreate:

```
docker compose -p edge -f deploy/edge/docker-compose.yml run --rm --no-deps caddy \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -p edge -f deploy/edge/docker-compose.yml up -d --force-recreate --wait
```

A site block whose proxy is not running answers 502 and leaves the other
sites alone. A hostname whose DNS does not point at the box yet gets no
certificate; Caddy retries and serves it once the record resolves.

## Cloudflare in front (ADR-0042)

All four hostnames are proxied by Cloudflare, which puts a managed challenge
in front of the `/app` of `uscode.linkedlegislation.org` and
`statutes.linkedlegislation.org`. The Caddy here takes the client address from `CF-Connecting-IP` when
the peer is in Cloudflare's ranges, and a hostname named in
`EDGE_CLOUDFLARE_ONLY` answers 403 to any other public peer. The box's own
probes come from the Docker bridge gateway, a private address, and are let
through.

### In Cloudflare (once)

1. **Add the zone.** Cloudflare dashboard › Add a domain ›
   `linkedlegislation.org`, Free plan. Cloudflare reads the zone's records from
   the current nameservers; compare its list with Route 53's hosted zone and
   add anything it missed (MX and TXT records in particular).
2. **Choose what is proxied.** In DNS › Records, set `uscode`, `statutes`,
   `reintro` and `codification` to **Proxied** (orange cloud): the four
   hostnames the edge serves. Leave every other record **DNS only** (grey). A
   record the import turned into CloudFront's addresses (an alias in Route 53)
   becomes a `CNAME` to the CloudFront name, DNS only.
3. **SSL/TLS › Overview:** encryption mode **Full (strict)**. The edge keeps
   its Let's Encrypt certificates, and Cloudflare checks them.
4. **SSL/TLS › Edge Certificates:** leave **Always Use HTTPS** off. The edge
   already redirects to HTTPS, and Let's Encrypt's HTTP challenge on `:80` has
   to reach it unredirected to renew a certificate.
5. **Security › Bots:** leave **Bot Fight Mode** off. On the Free plan it
   applies to every path with no exceptions, and it challenges API callers
   such as reintroductions-us, which cannot answer a challenge.
6. **Security › WAF › Custom rules › Create rule**, named `Challenge the
   readers`, action **Managed Challenge**, with this expression (Edit
   expression):

   ```
   (http.host in {"uscode.linkedlegislation.org" "statutes.linkedlegislation.org"}
    and starts_with(http.request.uri.path, "/app")
    and not starts_with(http.request.uri.path, "/app/healthz")
    and not cf.client.bot)
   ```

   `cf.client.bot` is Cloudflare's verified-bot list, Googlebot and Bingbot
   among them, so the landing pages in each site's `/sitemap.xml` stay
   reachable to them (ADR-0039 here, ADR-0098 there). `/api/v1` and the
   citation URL `/us/usc/…` are not challenged; a browser following a citation
   URL is redirected into `/app` and challenged there.
7. **Change the nameservers.** At the domain's registrar, replace the Route 53
   nameservers with the two Cloudflare names on the zone's overview page.
   Cloudflare emails when the zone is active, usually within an hour.

### On the box (after the zone is active)

Check that both hostnames answer through Cloudflare (`cf-ray` in the
headers), then lock them:

```
curl -sI https://uscode.linkedlegislation.org/health | grep -i '^cf-ray'
curl -sI https://statutes.linkedlegislation.org/health | grep -i '^cf-ray'

sudo -iu ec2-user
cd /home/ec2-user/statutes-at-large
git pull --ff-only
echo 'EDGE_CLOUDFLARE_ONLY=uscode.linkedlegislation.org statutes.linkedlegislation.org reintro.linkedlegislation.org codification.linkedlegislation.org' \
    >> deploy/edge/.env
docker compose -p edge -f deploy/edge/docker-compose.yml run --rm --no-deps caddy \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -p edge -f deploy/edge/docker-compose.yml up -d --force-recreate --wait
```

Then, from a machine off the box:

```
# 403: the box's address, around Cloudflare
curl -s -o /dev/null -w '%{http_code}\n' --resolve uscode.linkedlegislation.org:443:<the box's Elastic IP> \
    https://uscode.linkedlegislation.org/health
# 200: through Cloudflare
curl -s -o /dev/null -w '%{http_code}\n' https://uscode.linkedlegislation.org/health
```

Without `EDGE_CLOUDFLARE_ONLY` the Caddyfile behaves as before for a peer
outside Cloudflare, so the recreate that carries this file can happen before
the nameservers move. Removing the line and recreating undoes the lock;
setting the two records back to DNS only undoes the proxy.

The ranges in the Caddyfile are Cloudflare's published list on 2026-11-24
(https://api.cloudflare.com/client/v4/ips). Cloudflare announces a change to
it in advance; the list has not changed since 2021.

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
