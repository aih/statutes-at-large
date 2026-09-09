# ADR-0024: A relay to the shared cluster, and a quieter site-down alarm

Date: 2026-09-09. Status: accepted. Amends ADR-0017 (decisions 2 and 9) and
ADR-0023 (decision 2); the alarm and the watchdog are the deployment plan's
sections 2 and 8.

## Context

ADR-0023 attached this project's `api` container to the US Code compose
project's default network so it could reach that site's OpenSearch cluster at
`opensearch:9200`. Both projects name a service `api`, and Docker registers a
service's name as a DNS alias on every network its container joins. From the
deploy of `dd76171` at 16:36 UTC on 2026-09-09, `docker exec
uscode-redesign-frontend-1 getent hosts api` answered `172.18.0.8`, which is
`statutes-at-large-api-1`; that site's own `api` is `172.18.0.3`. The US Code
reader's `API_BASE_URL=http://api:8001` reached this site's API, which answers
404 for `/us/usc/…`. Its watchdog logged twelve failure runs with
`api=200 app=404` and restarted its services six times between 16:52 and 17:45
UTC, and its `uscode-site-down` alarm mailed on each pair of state changes.
Commit `d75ec7e` detached `api` and left search answering 503.

The mail the alarms produced is what prompted the review below.

## Decisions

1. **No service of this project joins another project's network under a name
   that project uses.** The US Code project's service names are `db`,
   `opensearch`, `redis`, `api`, `frontend` and `proxy` (its
   `docker-compose.prod.yml`). A container this project attaches to
   `uscode-redesign_default` carries its service name and its container name
   as aliases there, so the name is part of the interface between the two
   projects. `tests/test_compose_networks.py` reads
   `docker-compose.prod.yml` and asserts it: one service on that network, its
   name outside that set, and `api` on this project's network alone.

2. **`search-relay` is the one service on that network.** `alpine/socat`
   pinned at `1.8.1.3`, 32 MB, `restart: unless-stopped`, no published ports,
   `TCP-LISTEN:9200,fork,reuseaddr` forwarded to `TCP:opensearch:9200`. The
   API sets `SEARCH_URL=https://search-relay:9200` and `depends_on` it with
   `condition: service_started`. socat copies bytes, so the TLS session is the
   API's with the cluster and the certificate names neither host —
   `SEARCH_VERIFY_CERTS=false` already covers that (ADR-0023 decision 2). Its
   aliases on the foreign network are `search-relay` and
   `statutes-at-large-search-relay-1`. `caddy:2-alpine` is the other candidate
   and is ten times the size and has no layer-4 proxy without a plugin build.

3. **The watchdog publishes four metrics and one of them is alarmed.**
   `Statutes/SiteUp` as before, plus `ApiUp`, `AppUp` and `EdgeUp` in the same
   `put-metric-data` call. `EdgeUp` is 0 when curl exits 7 — a refused
   connection on 443 — on both probes. Only `SiteUp` has an alarm; the other
   three are what the recipient of the mail reads to see which half failed.

4. **A failed probe inside a deploy's window publishes `SiteUp=1`.**
   `deploy-on-box.sh` writes its start time to
   `${DATA_ROOT}/watchdog/deploying` under the deploy lock and removes it as
   it exits; the watchdog treats the file as current for 900 seconds. A probe
   that fails while it is current is logged, published as `SiteUp=1` with the
   real `ApiUp`, `AppUp` and `EdgeUp`, and not counted toward a restart.
   Publishing nothing was the alternative and is worse: missing data breaches,
   so a long deploy would page. The proxy is now recreated with `--wait`.

5. **The watchdog restarts the half that failed** — `api`, `frontend`, or both
   with `proxy` when neither surface answered. The proxy is the hop the two
   share; restarting it while one half is answering takes that half down too.
   A refused connection on 443 is the edge, and the watchdog restarts nothing
   and says so (ADR-0017 decision 9, until now only written down). The
   threshold of three consecutive failures, the 600-second cooldown and the
   deploy lock are unchanged.

6. **`statutes-site-down` alarms on five of the last seven one-minute
   periods** rather than five consecutive, keeps `treat-missing-data
   breaching`, and keeps its OK action. Five minutes down still pages, and so
   does a box that has stopped publishing. Two isolated minutes in seven no
   longer count as a run, and the alarm leaves ALARM only on three good
   minutes of seven, so a site that recovers in bursts mails one pair of
   messages rather than one pair per burst. The OK mail is how the recipient
   learns the site came back without going to look; the flapping, not the OK
   action, was the volume. The US Code site's `uscode-site-down` has the same
   shape and is not changed here.

## What the review found

- **The site's own alarm is not too sensitive.** `statutes-site-down` last
  changed state at 06:39 UTC on 2026-09-09, to OK, and has not alarmed since.
  Its watchdog log holds 30 failed probes and 3 restarts, all inside the
  cut-over between 06:1x and 06:39, and one single failed probe at 17:01
  (`api=502 app=200`) during a deploy, which recovered the next minute and
  never approached five. Every page it has sent was a real outage. The mail of
  2026-09-09 came from `uscode-alerts` — the collision above — and the fix for
  that is decisions 1 and 2, not a threshold.
- **A deploy does cost a probe.** Four deploys on 2026-09-09 (07:45, 15:42,
  16:35, 17:00 UTC), 40 to 60 seconds each, each recreating the proxy; one
  probe saw the 502. Decision 4 covers it.
- **The API's `--limit-concurrency 64` stays.** Nothing in the logs is a 503
  from it: load average 0.37, `api` at 137 MiB of its 512 MB limit. The
  evidence for changing it would be 503s at `/health` in the watchdog log with
  the box unloaded.
- **`statutes-at-large-db-1` at 649 MiB of 768 MB stays.** A Postgres
  container's memory is mostly reclaimable page cache, and the box shows no
  OOM kill in the kernel log and `RestartCount` 0 on every container, with
  2,563 MB available and 168 MB of swap used. The evidence for raising the
  limit would be `docker inspect --format '{{.State.OOMKilled}}'` true, or a
  restart count above 0.

## Consequences

- Search on this site answers again once the relay is deployed; nothing in
  `../uscode-redesign` changes, and neither site's compose file names a
  service of the other.
- Three custom metrics beyond `SiteUp`, at about $0.30 a month each, and one
  `PutMetricData` call a minute as before.
- The alarm's shape is applied by re-running `deploy/alarms.sh`; a
  `put-metric-alarm` upsert leaves the alarm's state history in place.
- A deploy killed with SIGKILL leaves the marker file behind, and the watchdog
  publishes `SiteUp=1` for a failed probe until 900 seconds after that
  deploy's start.
