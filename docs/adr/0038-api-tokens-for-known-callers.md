# ADR-0038: API tokens for known callers

Date: 2026-10-30. Status: accepted. The US Code site made the same change as
its ADR-0096.

## Context

reintroductions-us prepares a bill of one Congress for reintroduction in the
next and checks each Public Law the bill cites against this site:
`/api/v1/us/pl/{congress}/{number}[/s{section}]` for `currency.amended`, the
law's latest amendment. Those routes spend from `limit_text` (ADR-0030), 120
a burst and one a second per address, sized for a person reading pages. The
same checks run ahead of time over a Congress's bills are many times that,
and a caller on a cloud host shares its address with others.

## Decision

1. A token is sent as `Authorization: Bearer <token>`. `STATUTES_API_TOKENS`
   holds, per named token, the SHA-256 digest of the token and a `scale`, as
   JSON. Only the digest is configured; `scripts/api_token.py` shows the token
   once, for the caller.
2. A request carrying a configured token is keyed in every per-caller limiter
   (`text`, `cite`, `cited-by`, `labels`, `search`) as `token:<name>` rather
   than by address, and each budget is multiplied by the token's `scale`
   (default 10): the burst and the refill rate.
3. A bearer token that matches no configured token is a `401` with
   `WWW-Authenticate: Bearer`. A request with no `Authorization` header, or
   another scheme, is unchanged.
4. The token is read where a budget is applied; a route with no limiter
   ignores the header. A private or loopback caller is still outside
   `limit_text` whether or not it sends a token.
5. Revoking a token is removing its entry and restarting the API.

## Consequences

- The limits stay in the process; a token's bucket is per process.
- A token raises a caller's budget and grants nothing else.
- The proxy's crawler block (ADR-0030) applies before the API sees the token,
  so a token holder's User-Agent must not say `bot`, `crawler` or `spider`.
- Nothing records per-token use beyond the proxy's log.
