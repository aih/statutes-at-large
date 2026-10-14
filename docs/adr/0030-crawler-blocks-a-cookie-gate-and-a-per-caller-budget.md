# ADR-0030: crawler blocks, a cookie gate for the reader, and a per-caller budget for the text

Date: 2026-10-14. Status: accepted. The US Code site made the same three
changes under its ADR-0073, ADR-0088 and ADR-0029; this site had robots.txt
alone.

## Context

At 02:20 UTC on 2026-10-14 `statutes-api` went from about 0.01 requests a
second to 2.2–3.7, and the Grafana "Traffic spike" rule fired for it
(ADR-0029; the US Code site's ADR-0090). In the three hours to 03:03 UTC it
served 8,503 responses with status 200 and 24 with 503:

| Route | Requests |
|---|---|
| `/api/v1/us/pl/{congress}/{number}/{path}` | 4,036 |
| `/api/v1/cited-by` | 1,870 |
| `/api/v1/laws/{congress}/{number}` | 1,802 |
| `/api/v1/labels` | 276 |
| `/api/v1/us/stat/{volume}/{page}` | 213 |
| `/api/v1/us/sComp/{congress}/{number}/{path}` | 185 |

Of 120 sampled server spans from the last hour, 119 had `server.address` `api`:
the calls came from the reader rendering pages, not from callers of `/api/v1`.
The paths were one section each of Pub. L. 117-328 (`/dFF/tI/stB/ch2/s1220`,
`/dC/tVIII/s8110`, …), each with `laws/117/328`, `cited-by` and the section's
XML: a walk of every section of one law through `/app/us/pl/…`, about one page
a second. The spans carry no client address or User-Agent (ADR-0029), so
whether it declares itself, keeps cookies or rotates addresses is not known
from telemetry.

The proxy served `robots.txt` with `Disallow: /` and nothing else. The api's
per-address limits covered `cite`, `cited-by`, `labels` and `search`; the
reader forwards its reader's address on every call (gotcha 13), and
`cited-by`'s budget (2 a second) sat above one page a second.

## Decision

1. **Declared crawlers get 403 at the proxy.** The User-Agent list is the US
   Code site's, including the generic `bot`, `crawler` and `spider` markers.
   robots.txt is unchanged: it already disallows everything.
2. **The reader asks for a cookie.** `/app*` without `stat_h` gets a 403 page
   that sets it and reloads once. `/app/healthz`, `/app/_astro/*` and
   `/app/icons/*` are outside it. It applies to the hostname in `GATE_HOST`,
   which `docker-compose.prod.yml` sets to `statutes.linkedlegislation.org`;
   the Caddyfile's default `gate.invalid` matches nothing, so the dev stack and
   `make test-e2e` never meet it. `/api/v1` is not gated.
3. **The text of the laws has a per-caller budget**, `limit_text` in
   `params.py`: 120 calls, refilled at one a second, on the identifier routes
   (`/us/pl`, `/us/pvtl`, `/us/act`, `/us/sComp`), `/us/stat` and `/laws`. A
   reader page costs two or three calls, so the burst is about forty pages and
   the sustained rate about twenty a minute. Over it the api answers 429 with
   `Retry-After` and the reader passes both through. A private or loopback
   caller is exempt (`is_internal_caller`): the dev stack, and the reader's own
   calls when it has no address to forward.
4. **Both upstreams retry a failed dial for 25 s** (`lb_try_duration`), as the
   US Code site's ADR-0092 does, so a backend recreated by a deploy holds
   requests instead of answering 502.
5. **The deploy validates the Caddyfile and recreates the proxy only when it
   changed.** `caddy validate` runs with the proxy's image before anything on
   the box changes; a failure leaves the running stack as it was. The proxy
   is recreated when the file the running container sees differs from the
   repository's, as on the US Code site; before this every deploy recreated
   it.

## Consequences

- The deploy that carries this recreates the proxy (the Caddyfile and the
  proxy's environment both change), and the edge has no `lb_try_duration` of
  its own, so requests to statutes.linkedlegislation.org can answer 502 for
  the second or two the new proxy takes to start. Later deploys that leave the
  Caddyfile alone do not recreate it.
- Requests the proxy refuses never reach FastAPI and drop out of the
  telemetry; the spike alert clearing says the reader stopped rendering for
  them, not that the requests stopped.
- A scraper that keeps cookies and rotates addresses passes all three. The
  next steps the US Code site recorded (a proof-of-work interstitial, a CDN
  challenge) apply here too.
- A program reading many laws from one address through `/api/v1` meets the
  same budget, 60 a minute sustained.
