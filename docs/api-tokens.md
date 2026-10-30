# API tokens

A token raises one caller's rate limits on `/api/v1` (ADR-0038). It grants nothing else: every
route answers the same with or without one. The US Code site has the same design under its
ADR-0096; the two sites issue their tokens separately. This page covers making a token, storing
it on the box and with the caller, and sending it.

## Generate

`scripts/api_token.py` uses the standard library only, so it runs from any checkout, on a
workstation or on the box:

```bash
python3 scripts/api_token.py reintroductions --scale 20
```

```
token (give to the caller, store nowhere else): stat_Qm8…
STATUTES_API_TOKENS entry: {"reintroductions": {"sha256": "9f1c…", "scale": 20.0}}
```

- The **name** (`reintroductions`) identifies the caller. Its budgets are keyed on
  `token:reintroductions`, and the name appears nowhere in a response.
- The **scale** multiplies the burst and the refill rate of every per-caller budget the token
  meets. It defaults to 10 and must be at least 1.
- The **token** is printed once. The site keeps only its SHA-256 digest, so a lost token cannot
  be recovered; make a new one.

The per-caller budgets, before scaling:

| Budget | Routes | Burst | Sustained |
|---|---|---|---|
| `text` | the identifier routes (`/us/pl`, `/us/pvtl`, `/us/act`, `/us/stat`, `/us/sComp`), `/laws/…` | 120 | 1 a second |
| `cite` | `/cite` | 60 | 2 a second |
| `cited-by` | `/cited-by` | 60 | 2 a second |
| `labels` | `/labels` | 300 | 30 a second |
| `search` | `/search` | 120 | 10 a second |

At scale 20 the `text` budget is 2,400 a burst and 20 a second.

## Store on the box

The setting is `STATUTES_API_TOKENS` in the box's `.env`,
`/home/ec2-user/statutes-at-large/.env`. `docker-compose.prod.yml` passes it to the `api`
service. It is one line of JSON, with every token as one key, in single quotes:

```bash
STATUTES_API_TOKENS='{"reintroductions": {"sha256": "9f1c…", "scale": 20}, "another": {"sha256": "…", "scale": 10}}'
```

The single quotes keep the value literal for both Docker Compose and the `.env` reader the API
uses in development. Reach the box with `aws ssm start-session --target <instance-id>`
(`docs/plans/2026-09-08-deployment-plan.md`), edit the file as `ec2-user`, then recreate the API
so the container picks the new value up:

```bash
sudo -iu ec2-user
cd ~/statutes-at-large
"${EDITOR:-vi}" .env
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate --wait api
```

A `docker restart` keeps the old environment. A malformed entry (a digest that is not 64 hex
characters, a scale below 1, invalid JSON) stops the API at start-up, and `--wait` reports it;
fix the line and run the command again. The next deploy (`deploy/deploy-on-box.sh`) keeps the
setting, since `.env` is not in the repository.

In development, put the same line in the checkout's `.env` and restart `make dev`.

## Store with the caller

The token goes to the caller over a private channel and is kept as a secret: an environment
variable or a secret store, never a committed file. reintroductions-us reads it from
`STATUTES_API_TOKEN`; its `docs/api-tokens.md` covers that side.

## Use

Send it on every request as a bearer token:

```bash
curl -H "Authorization: Bearer $STATUTES_API_TOKEN" \
  "https://statutes.linkedlegislation.org/api/v1/us/pl/119/43"
```

```python
import httpx

client = httpx.Client(
    base_url="https://statutes.linkedlegislation.org/api/v1",
    headers={"Authorization": f"Bearer {token}"},
)
client.get("/us/pl/81/740/s3")
```

| Response | Meaning |
|---|---|
| `200`, `304`, `404` | As without a token |
| `401` with `WWW-Authenticate: Bearer error="invalid_token"` | The token is not configured: mistyped, revoked, or the API was not recreated after the edit |
| `429` with `Retry-After` | The token's scaled budget for that route is spent; wait that many seconds |
| `403` "closed to automated crawling" | The proxy refused the User-Agent (ADR-0030): one containing `bot`, `crawler` or `spider` is refused on every path, token or not |

A request with no `Authorization` header, or with another scheme such as `Basic`, gets the
anonymous budgets.

To check a token after installing it: the token answers `200` and any other bearer value
answers `401`.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $STATUTES_API_TOKEN" https://statutes.linkedlegislation.org/api/v1/us/pl/119/43
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer wrong" https://statutes.linkedlegislation.org/api/v1/us/pl/119/43
```

## Rotate and revoke

- **Revoke:** delete the token's key from `STATUTES_API_TOKENS` and recreate the API. The next
  request with it answers `401`.
- **Rotate:** generate a token under a new name (`reintroductions-2`), add it beside the old
  one, recreate the API, switch the caller, then remove the old key and recreate again.
- **Change the scale:** edit `scale` and recreate the API. The token stays the same.

Budgets live in the API process, so a recreate also empties every bucket.
