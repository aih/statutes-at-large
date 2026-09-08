# Deploying statutes.linkedlegislation.org

Date: 2026-09-08. Status: proposed. The shape is the US Code site's
(its ADR-0020, ADR-0035, `docs/deploy.md`): one EC2 instance in the same AWS
account and region running a standalone production compose file, Caddy
terminating TLS, Postgres on a separate EBS volume, images built by GitHub
Actions and pushed to ECR, deploys and updates dispatched over SSM. Design
section 8 allows the same box as the US Code site; this plan uses its own
box and says below what sharing would change.

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

| | monthly |
|---|---|
| `t4g.medium` (2 vCPU, 4 GB, arm64), on-demand | ~$25 |
| 20 GB gp3 root + 40 GB gp3 data volume, `DeleteOnTermination=false` on the data volume | ~$5 |
| ECR (two images, a few tags kept) | ~$1 |
| S3 bucket `statutes-linkedlegislation` (database dumps, source files) | under $1 |
| Elastic IP while attached, egress under 100 GB | $0 |

About $32 a month. No load-pass instance size: the whole load is an hour,
inside a `t4g.medium`'s CPU credit balance. 4 GB holds Postgres
(`shared_buffers=512MB`), FastAPI, the Node SSR process and Caddy.

Sharing the US Code site's `t4g.large` instead: add this repository's
`docker-compose.prod.yml` as a second project on the same box with its own
Postgres and data directory, and a second site block in that box's
Caddyfile (`statutes.linkedlegislation.org` → this stack's proxy is not
needed; Caddy on the box would reverse-proxy to `statutes-api:8001` and
`statutes-frontend:4321` on a shared network). It saves the instance cost
and couples the two sites' deploys, restarts and disk. Not chosen here.

## 2. What the repository needs before the first deploy

Files, all modelled on the US Code site's with `uscode` → `statutes`:

1. `docker-compose.prod.yml`, standalone: no published `5432`; `api` and
   `frontend` from `${ECR_REGISTRY}/statutes-api:${IMAGE_TAG}` and
   `statutes-frontend`, `build:` as the fallback; `db` on
   `${DATA_ROOT}/pgdata` with `shared_buffers=512MB`, `max_wal_size=2GB`,
   `shm_size: 512mb`; `api` with `${DATA_ROOT}/data:/app/data` (the
   downloaded volumes, zips, parquet shards and COMPS files persist across
   image changes), `--limit-concurrency 64`, a `/health` healthcheck;
   `frontend` with `API_BASE_URL=http://api:8001`, `USCODE_ORIGIN`, and a
   healthcheck; `proxy` publishing 80 and 443 with `SITE_ADDRESS` and
   `${DATA_ROOT}/caddy:/data`; `restart: unless-stopped` everywhere.
   `.env` on the box: `SITE_ADDRESS`, `POSTGRES_PASSWORD`, `DATA_ROOT`,
   `ECR_REGISTRY`, `IMAGE_TAG`, `GOVINFO_API_KEY`, `SITE_ORIGIN`,
   `USCODE_ORIGIN`, `BACKUP_BUCKET`.
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
4. `deploy/provision.sh` (security group 80 and 443, instance tagged
   `Name=statutes-site`, data volume, Elastic IP; idempotent),
   `deploy/bootstrap-box.sh` (Docker, git, the data volume found by
   elimination and formatted only when empty, the clone, `.env` kept when
   present, `install-crons.sh`), `deploy/deploy-on-box.sh` (ECR login, pin
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
   on the instance tagged `Name=statutes-site`, poll the command),
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
7. `deploy/Caddyfile`: `robots.txt` says `Disallow: /` today, copied from
   the US Code demo. Decide before the site is public; the plan keeps it
   until the corpus is loaded, then switches to `Allow: /` with a sitemap
   later.

## 3. AWS, once

Everything in `us-east-1`, the account that holds the US Code site
(ECR registry `739065237548.dkr.ecr.us-east-1.amazonaws.com`).

1. **IAM, by an identity that may create IAM resources** (the US Code
   site's `admin-grant.sh` pattern, run once and then detached): the
   instance role `statutes-site` with `AmazonSSMManagedInstanceCore`,
   `AmazonEC2ContainerRegistryReadOnly`, `cloudwatch:PutMetricData`, and
   `s3:GetObject`/`PutObject`/`ListBucket` on
   `arn:aws:s3:::statutes-linkedlegislation/*`; the instance profile of the
   same name; two ECR repositories `statutes-api` and `statutes-frontend`
   with a lifecycle rule keeping the last ten tags; the GitHub OIDC role
   `statutes-github-deploy` trusted by `repo:aih/statutes-at-large:*`, with
   ECR push on the two repositories, `ssm:SendCommand` and
   `ssm:GetCommandInvocation` on instances tagged `Name=statutes-site`, and
   `ec2:DescribeInstances`. The existing GitHub OIDC provider is reused.
2. **The bucket** `statutes-linkedlegislation` (private, versioning off, a
   lifecycle rule expiring `db/` objects after 60 days).
3. **The instance**: `bash deploy/provision.sh` (AL2023 arm64,
   `t4g.medium`, `HttpTokens=required`, `HttpPutResponseHopLimit=2`, 20 GB
   root, 40 GB data volume with `DeleteOnTermination=false`, the security
   group with 80 and 443 only, no SSH, an Elastic IP). It prints the IP.
4. **DNS**: an A record `statutes.linkedlegislation.org` → the Elastic IP,
   in the zone that already holds `uscode.linkedlegislation.org`. Caddy
   needs it resolving before it can get a certificate.
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

That installs Docker and git, mounts the data volume at
`/var/lib/statutes` with `pgdata`, `data`, `caddy` and `logs` under it,
clones `https://github.com/aih/statutes-at-large` into
`/home/ec2-user/statutes-at-large`, writes `.env` (mode 600) with a
generated `POSTGRES_PASSWORD`, and installs the cron file. Then the first
deploy is the same command continuous deploy uses:

```
bash deploy/deploy-on-box.sh <sha>
```

Caddy gets its certificate within seconds of the DNS record resolving. The
site is up and empty; `/api/v1/status` shows nothing loaded.

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

Losing the instance: `provision.sh` again (it reuses the data volume by
tag), `bootstrap-box.sh`, `deploy-on-box.sh`; the corpus is on the volume.
Losing the volume: the same, then `pg_restore` from the newest dump in
`s3://statutes-linkedlegislation/db/` (minutes), or section 5 from the
sources (about an hour plus the COMPS walk).

## Not in this plan

No CDN (the `immutable` headers make CloudFront a drop-in later), no
autoscaling, no multi-AZ, no RDS: one reconstructible database on one box.
