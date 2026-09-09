# ADR-0017: Two sites, one edge

Date: 2026-09-08. Status: accepted. Implements the deployment plan
(`docs/plans/2026-09-08-deployment-plan.md`, sections 1, 2 and 4) and
records where the built shape departs from the plan's words and from the
US Code site's conventions (its ADR-0020, 0029, 0035, 0073).

## Context

The site runs on the US Code site's `t4g.large` as a second compose
project. One process must own ports 80 and 443 for both hostnames, and the
address the API's rate limiter keys on has to survive two proxy hops (the
edge and the site's own Caddy) and a third inside the reader (the frontend
container calling the API on the reader's behalf).

## Decisions

1. **One edge Caddy, in this repository.** `deploy/edge/` holds a compose
   project named `edge`: one Caddy publishing 80 and 443, terminating TLS
   for `uscode.linkedlegislation.org` and `statutes.linkedlegislation.org`,
   forwarding each to `uscode-proxy:8000` or `statutes-proxy:8000` over an
   external Docker network named `edge`. Certificates live in
   `${DATA_ROOT}/edge-caddy`. `deploy/edge/up.sh` creates the network and
   brings the edge up; it is the one step that touches both sites, and it
   runs once. Neither site's deploy, watchdog or update touches the edge.

2. **What is shared and what is not.** Shared: the instance, the `edge`
   network, the edge Caddy and its certificate store, the instance role
   `uscode-site` (gaining one statement for this site's backup bucket).
   Not shared: each site's Postgres, data volume (`/var/lib/uscode`,
   `/var/lib/statutes`), images, Caddyfile, `robots.txt`, headers, deploy
   lock, logs, watchdog, cron file, backup bucket, memory limits
   (`statutes-db` 768 MB, `statutes-api` 512 MB, `statutes-frontend`
   384 MB, `statutes-proxy` 64 MB). Amended 2026-09-09: the US Code site's
   OpenSearch cluster is shared too (ADR-0023), reached over that project's
   default network `uscode-redesign_default`. One service of this project is
   attached to it — `search-relay`, 32 MB — and no other; a service of this
   project on that network answers there under its own name, and the names
   that project uses are its own (ADR-0024).

3. **The inner proxies trust the edge subnet, not `private_ranges`.** The
   plan wrote `trusted_proxies static private_ranges` with
   `header_up X-Forwarded-For {client_ip}`. On the dev stack a
   workstation's peer address is private on Linux (the bridge gateway) and
   on older Docker Desktop (`192.168.65.1`), so `private_ranges` would have
   trusted a workstation to name its own client and the forged-header check
   would fail. The `edge` network is created with the fixed subnet
   `10.83.0.0/24` (`EDGE_SUBNET` in `deploy/edge/up.sh`, outside Docker's
   default address pools), and both sites' Caddyfiles carry
   `trusted_proxies static 10.83.0.0/24`. `{client_ip}` is then the
   forwarded address only when the peer is the edge, which has already
   overwritten the header with `{remote_host}`, and the peer itself from
   any other caller. The same Caddyfile serves the dev stack and the box.
   Measured on the dev stack on 2026-09-08 (this machine's Docker Desktop
   presents the workstation as its public address, `160.1.205.190`): a
   forged `X-Forwarded-For` is keyed on the peer, 75 requests drain the
   `cite` bucket, and the next request answers 429 whatever the header
   says while a second address still answers 200.

4. **The reader forwards the browser's address.** Every server-side call
   in `frontend/src/lib/api.ts` takes `CallOptions.clientAddress`
   (`Astro.clientAddress`, read by `clientAddressOf` in each page) and sends
   it as `X-Forwarded-For`; uvicorn's `--forwarded-allow-ips *` reads it
   into `request.client.host`, so `cite` and `cited-by` are limited per
   reader (60 then 2 a second) and not per frontend container. A page with
   no address sends no header. `/app/healthz` answers 200 with no API
   call for the compose healthcheck and the watchdog.

5. **The site's own compose file is standalone and publishes nothing.**
   `docker-compose.prod.yml` has no `ports`; the proxy is reached only
   through the `edge` network alias `statutes-proxy`, and `SITE_ADDRESS`
   is `http://statutes.linkedlegislation.org:8000` (plain HTTP with host
   matching). `.env` on the box holds `SITE_ADDRESS`, `POSTGRES_PASSWORD`,
   `DATA_ROOT`, `ECR_REGISTRY`, `IMAGE_TAG`, `GOVINFO_API_KEY`,
   `SITE_ORIGIN`, `USCODE_ORIGIN`, `BACKUP_BUCKET`; the scripts derive the
   bare hostname from `SITE_ADDRESS`.

6. **Cut-over order.** Create the network first, `deploy/edge/up.sh
   --network-only` from this repository's checkout on the box: the US Code
   site's compose file declares it as external, and its deploy fails at
   `up` while the network is absent (measured 2026-09-09, before any
   container was touched). Then deploy the US Code site's `shared-edge`
   branch (its proxy stops publishing 80 and 443 and joins `edge`), run
   `deploy/edge/up.sh`, check the US Code site through the edge, then
   `deploy/deploy-on-box.sh <sha>` here. Rollback is the US Code site's proxy publishing 80 and 443 again
   with the edge stopped (its `docs/deploy.md`, "Sharing the box").

7. **`robots.txt` answers `Disallow: /` on both sites**, served by each
   inner Caddyfile; the edge serves none. Cross-site links are plain
   navigations, allowed in both directions (ADR-0016).

8. **`X-Forwarded-Proto`.** The edge sends `https`; each inner Caddy
   preserves it from the trusted peer and the inner hop itself is `http`.
   Nothing here reads it; the US Code site's cookie flag is decided by
   `USC_COOKIE_SECURE=true` and not by the scheme.

9. **Each watchdog stands down when nothing listens on 443.** Both probe
   through the edge with `--resolve <host>:443:127.0.0.1`; a refused
   connection is the edge being down, and restarting a site's own
   services would not answer it. The edge's liveness is compose's
   `restart: unless-stopped`. Each watchdog restarts its own `api`,
   `frontend` and `proxy`; the inner proxy is restarted with
   `docker compose restart`, which keeps the container and so its `edge`
   attachment and alias. Amended 2026-09-09 (ADR-0024): this site's
   `deploy/watchdog.sh` reads curl's exit 7 on both probes as the edge
   refusing connections, logs it and restarts nothing, and otherwise
   restarts the half that failed — `api`, `frontend`, or both with `proxy`
   when neither surface answered.

10. **The US Code site's side** is its branch `shared-edge` (three
    commits, not pushed): the proxy without `ports` on `edge` as
    `uscode-proxy`, its Caddyfile with the same trust rule, its deploy
    check and watchdog through the edge by hostname, `docs/deploy.md`
    section 9 "Sharing the box", its ADR-0020 and ADR-0029 amended, and
    `docs/verification/xff.md` with the measurement: from a peer on
    `10.83.0.0/24` a forged `X-Forwarded-For: 203.0.113.9` reaches the
    backend as `203.0.113.9`; from a peer on the project network it
    arrives as the peer.

11. **The edge's ports follow its site addresses.** Host port equals
    container port; bare hostnames listen on 80 and 443, the production
    defaults. A rehearsal names a port in the address
    (`http://statutes.localhost:8020`) and sets `EDGE_HTTP_PORT=8020`;
    `EDGE_HTTPS_PORT` is then bound and idle. The edge has no
    `trusted_proxies`, a 128 MB limit, and `deploy/edge/up.sh` refuses to
    reuse a network named `edge` whose subnet is not `EDGE_SUBNET`.

12. **Departures from the US Code site's scripts.** `bootstrap-box.sh`
    finds the data volume as the one disk that is neither the root disk
    nor mounted anywhere (the US Code volume is), refuses when there is
    more than one, and writes the fstab entry by UUID because two data
    volumes make NVMe order unstable. `provision.sh` creates the volume
    separately and attaches it as the first free `/dev/xvd[c-p]`, so
    `DeleteOnTermination` does not apply; the ECR lifecycle also expires
    untagged images after a day and the bucket aborts incomplete
    multipart uploads after two days. The OIDC role trusts every ref of
    `repo:aih/statutes-at-large` and is not granted `ssm:ListCommands`;
    `admin-grant.sh` stops when the OIDC provider or the `uscode-site`
    role is absent rather than creating them. `alarms.sh` creates two
    alarms (`statutes-site-down`, `statutes-disk-high`); the box's CPU,
    credit and status-check alarms exist already. `statutes-disk-high`
    reads `disk_used_percent` for `/var/lib/statutes`, which the box's
    CloudWatch agent does not publish yet. `deploy-on-box.sh` exits 1
    after the stack is up when no container of compose project `edge` is
    running; it never starts the edge. The shared shell helpers
    (`env_value`, `site_host`, `imds_instance_id`) are `deploy/lib.sh`.

## Consequences

- The edge is a fourth container on the box, about 20 MB. A deploy of
  either site never recreates it; a Caddyfile change in `deploy/edge/`
  is applied by `deploy/edge/up.sh` with the proxy recreated.
- The first deploy of this site before the DNS record resolves leaves
  the edge without a certificate for the new hostname; `deploy-on-box.sh`'s
  robots check fails and says so. The edge retries ACME on its own once
  the name resolves.
- The US Code site's rate limiter now keys on the address the edge
  forwards; its ADR-0029 decision 1 holds because the edge overwrites
  first. Its ADR-0020 is amended, not replaced.
- A rehearsal of the whole shape runs on a workstation without AWS:
  the edge on :8020 with plain-HTTP site addresses, each dev proxy joined
  to the `edge` network (`deploy/edge/README.md`). Run on 2026-09-08:
  both hostnames answered `/health`, `/app/healthz`, `robots.txt`
  (`Disallow: /`), `/app/us/pl/81/740/s3` and `/app/us/usc/t16/s45f/c/5`;
  the bare citation URLs redirected a browser into each reader; a forged
  `X-Forwarded-For: 203.0.113.9` reached the inner proxy as the edge's
  forwarded address (`18.238.109.121`, this workstation as Docker
  presents it) with the edge's own log showing `client_ip` equal to
  `remote_ip`; 75 `cite` requests answered 62 then 13 429s, the next was
  429 with any header, `/app/goto` was 429 on the same bucket, and
  another address answered 200; 26 Playwright tests passed over the
  edge.
- The api image's `COPY . .` now leaves `data/`, `.venv/`, `frontend/`
  and `.env` out (`.dockerignore`); the reader image leaves
  `node_modules`, `dist` and the test output out.
