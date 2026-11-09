# ADR-0039: Landing pages open to Google and Bing

Date: 2026-11-09. Status: accepted. The US Code site made the same change as
its ADR-0098, and reintroductions-us made it too.

## Context

The site is to be added to Google Search Console. `robots.txt` was
`Disallow: /` for every agent, the crawler pattern in `deploy/Caddyfile`
matches `Googlebot/2.1` and `bingbot/2.0` (its generic `bot/` marker), and the
cookie gate (ADR-0030) answers 403 to any `/app` request without `stat_h`,
which a crawler does not keep.

## Decision

1. `robots.txt` gains a group for `Googlebot` and `Bingbot` that allows `/`,
   `/app/`, `/app/about`, `/app/sources`, `/app/congress`, `/app/comps`,
   `/sitemap.xml`, `/favicon.svg`, `/app/_astro/` and `/app/icons/`, and
   disallows the rest. Rules on page paths end in `$`, so a page with a query
   string stays disallowed. The group for `*` is still `Disallow: /`. The file
   ends with `Sitemap: https://statutes.linkedlegislation.org/sitemap.xml`
   (`STAT_SITE_ORIGIN` overrides the origin).
2. `/sitemap.xml` is served by the proxy and lists the five pages.
   `tests/test_search_engines.py` fails when a listed page is not allowed by
   `robots.txt` or not in the exemption below.
3. The snippet `(search_engine_landing)` matches a request from Google's or
   Bing's published crawler ranges, for one of the paths in (1), with no query
   string. The crawler 403 and the cookie gate each carry
   `not { import search_engine_landing }`.
4. The ranges are `client_ip` lines in `deploy/searchbots/ranges.caddy`, not
   committed, written by `deploy/searchbot-ranges.sh` from Google's
   `googlebot.json` and Bing's `bingbot.json`. A list that does not parse or
   holds fewer than ten prefixes is refused and the previous file kept.
   `deploy-on-box.sh` runs it before validating the Caddyfile and recreates the
   proxy when the file changed.
5. The snippet always carries `client_ip 192.0.2.255/32`, a documentation
   address, so with no ranges file the matcher matches no request.

## Consequences

- A Googlebot User-Agent from any other address is refused as before.
- Law, section, page and compilation pages, the Congress pages and `/api/v1`
  stay closed to every crawler.
- The ranges are as current as the last deploy.
