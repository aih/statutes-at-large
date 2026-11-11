# ADR-0041: Token digests committed in `api-tokens.json`

Date: 2026-11-11. Status: accepted. Amends ADR-0038, decision 1.

## Context

ADR-0038 configures every token in `STATUTES_API_TOKENS` in the box's `.env`,
which takes a session on the box and a recreate of the API. The
codification-bills project fetches the enacted section and the Statute
Compilation section for each Code section of a title it drafts (about 1,300
for its first five titles) from cloud sessions, at the anonymous `text`
budget of one a second.

## Decision

1. `api-tokens.json` at the repository root holds token entries in the shape
   of `STATUTES_API_TOKENS`: a name, the SHA-256 digest, a scale. The API
   reads it at start-up beside the setting (`params.load_api_tokens`).
2. An entry in `STATUTES_API_TOKENS` replaces a committed entry of the same
   name. The box can lower a committed token's scale, or revoke it by giving
   the name another digest, without a commit.
3. The first committed entry is `codification-bills`, scale 10: `text` 1,200 a
   burst and 10 a second, `cite` 600 and 20 a second.
4. A committed token takes effect at the deploy that carries it.

## Consequences

- A digest is public. The tokens `scripts/api_token.py` makes carry 256 bits
  from `secrets.token_urlsafe(32)`, so the digest does not lead to the token.
- Adding, rescaling or removing a committed token is a pull request and a
  deploy.
- Measured before the change, from outside, 60 section requests at 10 at a
  time: mean 0.33 s to first byte, slowest 0.95 s, no errors.
