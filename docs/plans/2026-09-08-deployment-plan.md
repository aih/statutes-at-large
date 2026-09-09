# Deploying statutes.linkedlegislation.org

Date: 2026-09-08. Status: accepted 2026-09-09 (decisions: the US Code
site's box, an edge proxy, bots disallowed, cross-site links allowed). The
shape is the US Code site's (its ADR-0020, ADR-0035, `docs/deploy.md`): a
standalone production compose file, Postgres on its own EBS volume, images
built by GitHub Actions and pushed to ECR, deploys and updates dispatched
over SSM. Design section 8's second option is taken: this site runs on the
US Code site's `t4g.large`, as a second compose project behind one edge
proxy that terminates TLS for both hostnames.

## 0. What is measured

| | |
|---|---|
| Source volumes on the Hub | 137 files, 5 to 45 MB each (`docs/verification/era-sweep.md`), about 2.7 GB in all |
| Volume load time | 8 to 14 s per volume of 15 to 31 MB on this machine; about 45 to 60 minutes for all 137 |
| PLAW, 113th to 119th Congress | 2,149 laws, 63 s from the zips; 50 MB of zips |
| Citation index | 1,081,463 rows, 405 s from the three parquet shards (183 MB) |
| Classification mirror | 144,885 rows, 78 s, paced at ten requests a second |
| COMPS | 2,685 packages on GovInfo, two API calls each; the API allows 1,000 calls an hour, so the first walk takes about six hours and is resumable |
| Dev Postgres today | 792 MB for 5 volumes, 7 congresses and both indexes; `citations` 342 MB, `units` 257 MB, `laws` 117 MB |
| Full corpus estimate | 6 to 10 GB of Postgres, 3 GB of source files |

The database is a pure function of the sources and the loaders, all of them
idempotent per volume, package or file, so it is reconstructible in about
an hour plus the COMPS walk.

## 1. Shape and cost

```
:443 ── edge (Caddy, TLS for both names, compose project `edge`)
         ├── uscode.linkedlegislation.org   → uscode-proxy:8000   (the US Code site's own Caddy)
         └── statutes.linkedlegislation.org → statutes-proxy:8000 (this site's own Caddy)
```

Three compose projects on the box, on one external Docker network named
`edge`: the US Code site (`~/uscode-redesign`), this site
(`~/statutes-at-large`), and the edge (`deploy/edge/` in this repository,
checked out beside them). Each site keeps its own Caddyfile, robots,
headers and `/app*` routing; its proxy no longer publishes a port and is
reached by the edge through the network alias `uscode-proxy` or
`statutes-proxy`. The edge changes only when a hostname is added.

Client addresses: the edge overwrites `X-Forwarded-For` with the real peer
(the US Code site's ADR-0029, decision 1); each inner Caddy sets
`header_up X-Forwarded-For {client_ip}`, which is the forwarded address
when the peer is a trusted proxy (`trusted_proxies static private_ranges`,
which the edge is) and the peer itself otherwise, so the same Caddyfile
serves the dev stack and the box. Each API's rate limiter keys on that.

Protections per application:

| | |
|---|---|
| Data | a second EBS volume, 40 GB gp3, at `/var/lib/statutes`, `DeleteOnTermination=false`; the US Code site's volume and its usage alarm are untouched |
| Database | this site's own Postgres container, `shared_buffers=256MB`, no published port |
| Memory | compose `mem_limit`: `statutes-db` 768 MB, `statutes-api` 512 MB, `statutes-frontend` 384 MB, `statutes-proxy` 64 MB; about 1.3 GB beside the US Code site's ~5 GB on 8 GB |
| CPU | the one-hour initial load under `nice -n 10`; the credit-balance alarm already exists on the box |
| Deploys | separate repositories, locks (`${DATA_ROOT}/deploy.lock` per site), logs and image tags; a deploy of one site never recreates the other's containers or the edge |
| Watchdog | each site's watchdog probes its own hostname through the edge and restarts only its own services; the edge is restarted by neither |
| Backups | `pg_dump` to `s3://statutes-linkedlegislation/db/`, a bucket of its own |
| Bots | `robots.txt` answers `Disallow: /` on both sites |
| Cross-site links | plain navigations between the two hostnames, allowed by both sites' CSP (`form-action` and `connect-src` govern forms and scripts, not links) and `Referrer-Policy: strict-origin-when-cross-origin`; the US Code site's server-side `labels` call reaches this site through the public hostname and arrives with the box's own address, within the server-sized `labels` limit |

Cost above the existing box: the 40 GB volume (~$3), ECR for two images
(~$1), the bucket (under $1). About $5 a month.

## 2. What the repository needs before the first deploy

Files, all modelled on the US Code site's with `uscode` → `statutes`:

1. `docker-compose.prod.yml`, standalone: no published ports at all;
   `api` and `frontend` from `${ECR_REGISTRY}/statutes-api:${IMAGE_TAG}`
   and `statutes-frontend`, `build:` as the fallback; `db` on
   `${DATA_ROOT}/pgdata` with `shared_buffers=256MB`, `max_wal_size=2GB`,
   `shm_size: 256mb`; `api` with `${DATA_ROOT}/data:/app/data` (the
   downloaded volumes, zips, parquet shards and COMPS files persist across
   image changes), `--limit-concurrency 64`, a `/health` healthcheck;
   `frontend` with `API_BASE_URL=http://api:8001`, `USCODE_ORIGIN`, and a
   healthcheck; `proxy` with `SITE_ADDRESS=http://statutes.linkedlegislation.org:8000`
   (plain HTTP behind the edge), on the external `edge` network with the
   alias `statutes-proxy`; `mem_limit` per service; `restart:
   unless-stopped` everywhere. `.env` on the box: `SITE_ADDRESS`,
   `POSTGRES_PASSWORD`, `DATA_ROOT`, `ECR_REGISTRY`, `IMAGE_TAG`,
   `GOVINFO_API_KEY`, `SITE_ORIGIN`, `USCODE_ORIGIN`, `BACKUP_BUCKET`.
   `deploy/edge/` holds the edge: a compose file with one Caddy publishing
   80 and 443, `${DATA_ROOT}/edge-caddy:/data` for certificates, and a
   Caddyfile with two site blocks (`uscode.linkedlegislation.org` →
   `uscode-proxy:8000`, `statutes.linkedlegislation.org` →
   `statutes-proxy:8000`, each `header_up X-Forwarded-For {remote_host}`,
   `header_up Host {host}`), plus `deploy/edge/up.sh` creating the network
   and bringing the edge up.
2. `frontend/src/pages/healthz.astro` answering 200 with no API call, for
   the compose healthcheck and the watchdog.
3. The reader forwards the browser's address on its server-side API calls
   (`X-Forwarded-For` from `Astro.clientAddress` in `api.ts`), and the API's
   `client_key` reads it: `cite` and `cited-by` are limited per address
   (60 then 2 a second, sized for a person), and today every reader
   request reaches the API from the frontend container's one address, so
   one bucket would be shared by every reader of `/app/goto` and every
   "cited by" panel. Caddy already overwrites `X-Forwarded-For` at the
   edge, so the value the frontend forwards is the one Caddy set.
4. `deploy/provision.sh` (the second data volume attached to the existing
   instance tagged `Name=uscode-site`, the bucket, the ECR repositories;
   idempotent), `deploy/bootstrap-box.sh` (the new volume found by
   elimination and formatted only when empty, mounted at
   `/var/lib/statutes`, the clone beside `~/uscode-redesign`, `.env` kept
   when present, `install-crons.sh`; Docker and git are already there), `deploy/deploy-on-box.sh` (ECR login, pin
   `IMAGE_TAG`, pull, `alembic upgrade head` with the new image before it
   serves, `up -d --wait`, recreate the proxy so the bind-mounted Caddyfile
   is re-read, `robots.txt` check, prune; `flock`-guarded; logs to
   `${DATA_ROOT}/logs/deploy.log`), `deploy/update-sources.sh` (section 6),
   `deploy/install-crons.sh`, `deploy/watchdog.sh` (probe `/health` and
   `/app/healthz` through the proxy every minute, restart after three
   failures), `deploy/alarms.sh` (CPU, credit balance, status check, bytes
   out, data-volume usage to an SNS topic).
5. `.github/workflows/ci.yml` (`make test` and `make test-web` on every
   push and pull request; `make test-e2e` is not in CI, it needs a running
   site), `deploy.yml` (on CI success on `main` and on dispatch: build both
   images on `ubuntu-24.04-arm`, push to ECR tagged `<sha>` and `latest`,
   SSM `git checkout --force <sha> && bash deploy/deploy-on-box.sh <sha>`
   on the instance tagged `Name=uscode-site`, poll the command),
   `update-sources.yml` (section 6).
6. Two small ingest additions for the weekly run: `python -m ingest
   fetch-statute --if-changed` compares each volume's Hub file
   (`/api/datasets/dreamproit/us-statutes-at-large/tree/main/xmls`, sha
   and size) with the stored copy and downloads only what changed, and
   `python -m ingest statute --changed-only` loads only volumes whose file
   changed since their `source_checks` row; `python -m ingest citations
   --from-hub --if-changed` skips the reload when the dataset revision
   matches the one `/status` reports. Each writes a `source_checks` row
   either way, so `/status` stays honest about when the source was asked.
7. `deploy/Caddyfile`: `robots.txt` keeps `Disallow: /` (decided);
   `header_up X-Forwarded-For {client_ip}` replaces `{remote_host}` so
   the address the edge forwards survives the inner proxy.
8. The US Code site, on a branch of `../uscode-redesign`: its prod
   compose's `proxy` stops publishing 80 and 443, joins the external `edge`
   network with the alias `uscode-proxy`, and takes
   `SITE_ADDRESS=http://uscode.linkedlegislation.org:8000`; its Caddyfile
   uses `{client_ip}` the same way; its `deploy-on-box.sh` robots check and
   its watchdog probe go through the edge with the hostname; its
   `frontend` gains `STATUTES_ORIGIN=https://statutes.linkedlegislation.org`
   once `statutes-links` is merged; `docs/deploy.md` gains a section on the
   shared box. Its ADR-0020 is amended, not replaced.

## 3. AWS, once

Everything in `us-east-1`, the account that holds the US Code site
(ECR registry `739065237548.dkr.ecr.us-east-1.amazonaws.com`).

1. **IAM, by an identity that may create IAM resources** (the US Code
   site's `admin-grant.sh` pattern, run once and then detached): a
   statement on the existing instance role `uscode-site` for
   `s3:GetObject`/`PutObject`/`ListBucket` on
   `arn:aws:s3:::statutes-linkedlegislation` and `/*`; two ECR
   repositories `statutes-api` and `statutes-frontend` with a lifecycle
   rule keeping the last ten tags; the GitHub OIDC role
   `statutes-github-deploy` trusted by `repo:aih/statutes-at-large:*`, with
   ECR push on the two repositories, `ssm:SendCommand` and
   `ssm:GetCommandInvocation` on the instance tagged `Name=uscode-site`,
   and `ec2:DescribeInstances`. The existing GitHub OIDC provider and
   instance are reused.
2. **The bucket** `statutes-linkedlegislation` (private, versioning off, a
   lifecycle rule expiring `db/` objects after 60 days).
3. **The volume**: `bash deploy/provision.sh` creates a 40 GB gp3 volume
   with `DeleteOnTermination=false` in the instance's availability zone and
   attaches it to the instance tagged `Name=uscode-site`. The security
   group (80 and 443, no SSH) and the Elastic IP already exist.
4. **DNS**: an A record `statutes.linkedlegislation.org` → the box's
   Elastic IP, in the zone that already holds
   `uscode.linkedlegislation.org`. The edge needs it resolving before it
   can get a certificate.
5. **GitHub**: repository variable `AWS_DEPLOY_ROLE_ARN` = the OIDC role's
   ARN. No long-lived AWS keys in the repository. `GOVINFO_API_KEY` is not a
   GitHub secret; it lives only in the box's `.env`.

## 4. The box, once

`aws ssm start-session --target <instance-id>`, then:

```
SITE_ADDRESS=statutes.linkedlegislation.org \
ECR_REGISTRY=739065237548.dkr.ecr.us-east-1.amazonaws.com \
BACKUP_BUCKET=statutes-linkedlegislation \
GOVINFO_API_KEY=… \
  sudo -E bash bootstrap-box.sh
```

That mounts the new volume at `/var/lib/statutes` with `pgdata`, `data`,
`caddy`, `edge-caddy` and `logs` under it, clones
`https://github.com/aih/statutes-at-large` into
`/home/ec2-user/statutes-at-large`, writes `.env` (mode 600) with a
generated `POSTGRES_PASSWORD`, and installs the cron file.

The cut-over to the edge is the one step that touches the US Code site,
and it is one short interruption: `bash deploy/edge/up.sh --network-only`
(the `edge` network, which the US Code site's compose file declares as
external and needs before its deploy can run), deploy the US Code site's
branch (its proxy stops publishing 80 and 443 and joins the network), then
`bash deploy/edge/up.sh` (the edge Caddy on 80 and 443, the certificate
for `uscode.linkedlegislation.org` re-issued to the edge's own store). Check the US Code site through the edge before going on. Then the
first deploy of this site is the same command continuous deploy uses:

```
bash deploy/deploy-on-box.sh <sha>
```

The edge gets the second certificate within seconds of the DNS record
resolving. The site is up and empty; `/api/v1/status` shows nothing
loaded.

## 5. Loading everything

Inside the `api` container, in this order, each step resumable and
idempotent. Run it detached and read the log:

```
C="docker compose -f docker-compose.prod.yml exec -T api uv run python -m ingest"
$C fetch-statute 1-137                        # ~2.7 GB from the Hub, kept on the data volume
$C statute --volumes 1-137 --report data/verification   # ~1 hour; per-volume reports
$C plaw fetch 113-119 && $C plaw load 113-119 --report data/verification   # ~2 minutes
$C citations --from-hub --report data/verification      # ~7 minutes
$C classifications --report data/verification           # ~2 minutes
$C comps poll --limit 400                     # repeat until the walk reports nothing due; ~6 hours over the API's 1,000 calls an hour
```

`make load-all` is the first two lines; the plan adds a `make load-prod`
target that runs the whole sequence with the compose prefix. The site
serves every law as soon as its volume is loaded, so nothing waits for the
end. When `/status` shows 137 `STATUTE` volumes, seven `PLAW` congresses
and the two indexes, take the first dump:

```
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U statutes -Fc statutes \
  | aws s3 cp - s3://statutes-linkedlegislation/db/statutes-$(date +%F).dump
```

Order of the two PLAW-era loads does not matter (ADR-0011); the volume
load leaves PLAW-derived laws alone and lists them.

Smoke test from a workstation, not the box:

```
S=https://statutes.linkedlegislation.org
curl -sL -o /dev/null -w '%{http_code} %{url_effective}\n' -H 'Accept: text/html' "$S/us/pl/104/333/s814"
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' -H 'Accept: application/json' "$S/us/pl/81/740/s3"
curl -sD - -o /dev/null "$S/api/v1/us/pl/81/740/s3" | grep -i cache-control
curl -sG "$S/api/v1/cite" --data-urlencode 'q=Pub. L. 104-333, § 814' | jq .exists
curl -s "$S/api/v1/status" | jq '.collections.STATUTE.packages_loaded, .stale'
cd frontend && BASE_URL=$S npx playwright test
```

Then set `STATUTES_ORIGIN=https://statutes.linkedlegislation.org` on the
US Code site's `frontend` service once its `statutes-links` branch is
merged (ADR-0016).

## 6. The weekly update

`deploy/update-sources.sh`, run on the box, `flock`-guarded, logging to
`${DATA_ROOT}/logs/update-<date>.log`, every step inside the `api`
container. The sources change at different rates, so each step asks its
source what changed and does nothing when the answer is nothing:

| Step | Command | Cost when nothing changed | What changes it |
|---|---|---|---|
| 1 | `plaw poll --report data/verification` | 8 listing requests, one `source_checks` row (12 s measured) | new public laws, GovInfo re-issuing a file |
| 2 | `comps poll --since <last check − 1 day>` | one collection call | a compilation updated on GovInfo |
| 3 | `fetch-statute 1-137 --if-changed` then `statute --changed-only --report data/verification` | one Hub tree listing | a volume reprocessed on the Hub (design stage 6) |
| 4 | `citations --from-hub --if-changed --report data/verification` | one Hub revision call | a new US Code release point in `dreamproit/uscode` (a few dozen a year; the reload is 7 minutes) |
| 5 | `classifications --report data/verification` | one listing call; unchanged tables skipped | OLRC editing a table (the US Code site mirrors it first) |
| 6 | `pg_dump` to `s3://statutes-linkedlegislation/db/`, only when a step above wrote rows | nothing | |
| 7 | `curl /api/v1/status` into the log; `stale` must be false | one request | |

A typical week is under a minute of work and ten requests. Every step
writes its check row whether or not it loaded anything, so `/status`'s
`stale` flag (a week without a check) is the alarm for a schedule that
stopped running.

Two schedules, failing independently (the US Code site's ADR-0036 shape):

- `.github/workflows/update-sources.yml`, Mondays 07:53 UTC and on
  dispatch, one SSM command with `executionTimeout` 4 hours, polled for up
  to 5.5 hours. Logs in the Actions run and on the box.
- `/etc/cron.d/statutes` from `deploy/install-crons.sh`: the same script
  Thursdays 06:41 UTC as the backstop, the watchdog every minute, and
  `docker image prune` weekly.

A run interrupted by a deploy resumes on the next schedule: every loader
is idempotent per volume, package or file, and the dump happens only after
a successful pass.

## 7. Continuous deploy

A push to `main` runs CI; on success `deploy.yml` builds both images on
arm64, pushes them tagged with the sha, and runs `deploy-on-box.sh <sha>`
over SSM. The box checks out the exact commit it deploys. A deploy is a
migration with the new image, then `up -d --wait`, then the proxy recreated
so a Caddyfile change takes effect. Rollback is `deploy-on-box.sh <older
sha>` from a workstation with the deploy role, or `workflow_dispatch` on an
older commit.

## 8. Alarms and recovery

`bash deploy/alarms.sh <instance-id>` with `ALERT_EMAIL` set: CPU credit
balance, status check, bytes out, data-volume usage, and the watchdog's
`Statutes/SiteUp` metric. Confirm the SNS subscription from the mailbox.

Losing the instance is the US Code site's runbook first (its
`provision.sh` reuses both data volumes by tag), then `bootstrap-box.sh`,
`deploy/edge/up.sh` and `deploy-on-box.sh` here; the corpus is on the
volume.
Losing the volume: the same, then `pg_restore` from the newest dump in
`s3://statutes-linkedlegislation/db/` (minutes), or section 5 from the
sources (about an hour plus the COMPS walk).

## Not in this plan

No CDN (the `immutable` headers make CloudFront a drop-in later), no
autoscaling, no multi-AZ, no RDS: one reconstructible database on one box.
