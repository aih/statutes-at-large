# ADR-0042: Cloudflare in front of the two readers

Date: 2026-11-24. Status: accepted. Amends ADR-0017 (the edge trusts no proxy)
and ADR-0030 (the cookie gate).

## Context

ADR-0030 gave this site the US Code site's defences: a 403 for declared
crawlers, a cookie gate on `/app`, per-caller budgets. Both sites' records
named the case they leave open: a scraper that keeps cookies.

The US Code site's edge log in Grafana (its ADR-0097) shows that case. For
06:30–08:00 UTC on 2026-11-24, 62,725 requests reached
`uscode.linkedlegislation.org`, every one with an ordinary Chrome or Firefox
User-Agent, almost all from ISP networks, more than 500 distinct addresses
in one ten-minute window. After the gate's 403 the next request names the gate
page as its referer: the client runs the reload script and keeps the cookie.
Reader pages served went from 103,189 a day (2026-11-17) to 234,532
(2026-11-23), and reader 5xx from 184 to 3,783 a day. A burst of 27,180
requests in ten minutes at 07:10 coincided with the site-down alarm,
07:05–07:59. On 2026-11-22 the statutes API took 12.4 requests a second.

Blocking addresses or networks does not reach a crawler spread over
residential addresses, and a cookie or proof-of-work check costs a headless
browser little.

## Decision

1. Cloudflare proxies `uscode.linkedlegislation.org` and
   `statutes.linkedlegislation.org`, Free plan, SSL mode Full (strict), with
   one WAF custom rule: a Managed Challenge on `/app` except `/app/healthz`,
   for clients that are not on Cloudflare's verified-bot list. Bot Fight Mode
   stays off, since it cannot exempt `/api/v1`. The other hostnames stay DNS
   only. The steps are in `deploy/edge/README.md`.
2. The edge trusts Cloudflare's published ranges (`trusted_proxies static`,
   `client_ip_headers CF-Connecting-IP`) and forwards `{client_ip}` instead of
   `{remote_host}`. For a peer outside those ranges `{client_ip}` is the peer,
   so nothing changes for a hostname Cloudflare does not proxy.
3. A hostname in `EDGE_CLOUDFLARE_ONLY` answers 403 to a public peer outside
   Cloudflare's ranges, so the challenge cannot be skipped by calling the box's
   address. Private ranges are let through for the box's own probes. Unset,
   nothing is locked, so the file can be deployed before the nameservers move.
4. The cookie gates, crawler 403s and per-caller budgets of both inner proxies
   stay as they are.

## Consequences

- The domain's nameservers move from Route 53 to Cloudflare, which then holds
  every record of `linkedlegislation.org`.
- A reader may see Cloudflare's challenge page before the first page.
- The ranges are written into the Caddyfile twice. A change Cloudflare
  publishes needs an edit of both and a recreate of the edge.
- API callers reach `/api/v1` through Cloudflare unchallenged, and their
  addresses still reach the per-caller budgets.
- Not covered by this: a crawler that solves Cloudflare's challenge. Cloudflare's
  Free plan rate-limiting rule is the next step if one does.
