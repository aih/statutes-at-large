# BUILDLOG

One entry per session: what was asked, what was decided, what was verified.

## 2026-09-07 — stage 1: schema, repository, STATUTE loader

Asked: build stages 1 and 2 of the statutes API design in a new repository.

Done in this session by the main agent:

- Schema (`db/models.py`, migration `5afe43f05819`), the `Repository` protocol
  and its SQLAlchemy implementation, identifier parsing, `params.py`, the
  citation redirector, the app skeleton.
- The STATUTE volume loader with the section-7 identifier rules, the numbering
  pass for colliding law numbers, and the load report.
- Volumes 64 and 124 loaded into Postgres; reports in `docs/verification/`.
- 64 tests over SQLite and verbatim slices; `make test` and `make test-slow`
  green.

Decisions: ADR-0001 to ADR-0005.

Verified: `make test-all` (64 passed); `python -m ingest statute` over volumes
64, 72, 124, 137 (counts in `docs/verification/README.md`; 72 and 137 parsed
but not committed as reports because only 64 and 124 were asked for).

## 2026-09-07 — stage 2: API routes, COMPS, the two views

Two subagents in worktrees, each with its own tests, merged by the main agent:

- Enacted-view routes (`api/routes.py`, `api/schemas.py`, `api/responses.py`,
  `tests/test_api.py`, 34 tests): `/api/v1/us/pl|pvtl|act`, `/us/stat`,
  `labels`, `status`, `laws/{c}/{n}[/sections/{num}]`; ETag, `If-None-Match`,
  `Cache-Control` per design section 5.
- COMPS (`ingest/govinfo.py`, `ingest/comps.py`, `api/comps.py`, 48 tests):
  the GovInfo client, parser, loader with `comp_versions`, the poller, the
  `comps` CLI, `/us/sComp/…`, `/comps`. Live: four packages loaded, one poll.

Main agent after the merge: `alternatives` for the enacted view
(`api/alternatives.py`), `view=compiled` served through the counterpart,
level-aware note wording in `params.py`, the loader fixes the era sweep found
(Roman chapter numbers, several `pLaw` per component, chapter in the preface,
repeated laws), volumes 26 and 68 loaded so the Sherman Act and the Atomic
Energy Act meet their compilations in tests and in Postgres.

Decisions: ADR-0006 (restated acts), ADR-0007 (compilations).

Verified: `make test` 153 passed; `make test-slow` over volumes 64, 72, 116,
124, 137; the compose stack on :8010 serving both views from Postgres.

## 2026-09-08 — stage 3: the citation index, the classification mirror, `cited-by`, `currency.amended`

Asked: build design stage 3 (sections 4, 5 and 6): the `citations` table from
`dreamproit/uscode`, the `classifications` mirror, `GET /api/v1/cited-by`,
and `currency.amended.status` from evidence.

Main agent first: the schema (`citations`, `classification_files`,
`classifications`, `classification_source_checks`; migration `4381d4019386`),
the `Repository` index methods (`cited_by`, `source_credit_evidence`,
`classification_rows`, `classification_amendments`, `index_coverage`,
`enacted_dates`, the two statuses), the citations loader (`python -m ingest
citations --from-hub | --from-dir`, one row per `<ref href>` and per `<a href>`
in revision-note tables, replaced per US Code title, a `USCODE` source check
with the dataset revision), a 57-row parquet fixture cut by
`scripts/extract_citations_fixture.py`, `amended_sentence` and `cited_by_note`
in `params.py`, pyarrow in a `dataset` dependency group.

Two subagents in worktrees, neither touching `storage/`, `db/` or `params.py`:

- (a) `ingest/classifications.py` (`python -m ingest classifications
  [--congress N] [--from-dir PATH] [--force] [--report DIR]`): the US Code
  site's `classifications/tables` listing and `entries` pages, paced at ten
  requests a second, 429 waited out, 5xx retried; one `classification_files`
  row per `pl` table, replaced wholesale when the rows' hash changes, skipped
  when the listing matches what is stored; a check row per run. `GET
  /api/v1/cited-by` (`api/cited_by.py`), and `citations` and `classifications`
  blocks on `/status`. Fixtures: the listing and the first 40 rows of tables
  118-2 and 104 (`tests/fixtures/classifications/`). 30 tests.
- (b) `api/currency.py`: `decide` over the three evidence calls, `later` by
  (congress, number) then by date, `latest`, the codified alternative from the
  index; `LatestOut`, `AmendedOut.of`, `LabelCurrencyOut.amended`. 18 tests,
  with classification rows inserted for the module.

Main agent after the merge: one ADR-0010 from the two drafts, README,
this entry; the full `current` config and the 31 `pl` tables loaded into the
dev Postgres (`docs/verification/citations.json`, `classifications.json`);
the compose stack on :8010 checked on `/us/pl/83/703/s1`,
`/us/act/1890-07-02/ch647/s1` and `cited-by?identifier=/us/pl/104/333/s814`.

Decisions: ADR-0008 (the citation index: `current` config, one row per ref,
replaced per title), ADR-0009 (the tables mirrored through the US Code
site's API), ADR-0010 (`currency.amended` at request time; the classification
rule is a join).

Verified: `make test` 220 passed, 5 deselected, no network; the citation load
over Postgres in 405 s (1,081,463 rows); the mirror in 78 s (144,885 rows,
31 files, 104th to 119th Congress).

## 2026-09-08 — stage 4: public laws from PLAW bulk data

Asked: build design stage 4 (sections 2, 6 and 9): PLAW packages from the
113th Congress onward from GovInfo bulk-data USLM, replacing the
volume-derived units for those laws, with a poller and the PLAW collection on
`/status`.

Main agent first: `ingest/plaw.py` (one `pLaw` file to a `LawRecord` with
GPO's identifiers read from the XML, `provenance_identifiers = "gpo-uslm"`,
the rules-1.0 fallback for levels the file leaves unidentified, counted per
level; the citation, volume and pages from `citableAs`, the running-head
instruction and the page markers; quoted sections skipped; `python -m ingest
plaw fetch | load` from the per-congress zip, a directory, or files;
`make fetch-plaw`, `make plaw`), the precedence in `ingest/load.py:
_write_law` (`SOURCE_PRECEDENCE`, `WriteOutcome`, `laws_kept_from_plaw`,
compilations re-pointed), the identifier comparison per level written to
`docs/verification/plaw-{congress}.json`, `Repository.law_sources` and the
PLAW `collection_status` by congress. Fixtures: four whole bulk-data files and
the listings (`tests/fixtures/plaw/`); the 137 slice gains 118-3 so one law
stays volume-derived in the test database. 20 tests.

Two subagents in worktrees, neither touching `storage/`, `db/` or `params.py`:

- (a) `ingest/plaw_poll.py` (`python -m ingest plaw poll [--congress N]
  [--since YYYY-MM-DD] [--force] [--limit N] [--from-dir PATH] [--report DIR]
  [--json]`): the bulk listings against the stored `laws` rows; a file is due
  when no PLAW-derived row has its package id, when the listing time is later
  than `loaded_at`, or under `--force`; a congress with nothing PLAW-derived
  or more than half its files due is loaded from its zip, otherwise file by
  file with a commit per law; one `PLAW` check row per run. `make plaw-poll`.
  17 tests over respx and the fixture directory.
- (b) the API side: `ProvenanceOut` names the three identifier provenances,
  `CollectionStatusOut` gains `congresses` and `laws_by_congress`,
  `GET /api/v1/laws/{c}/{n}` gains `sources` (`LawSourcesOut`), README's
  route table, stage 4 paragraph and "Not yet served". 6 tests, including
  `alternatives` and `view=compiled` over a PLAW-derived unit with a
  compilation inserted for the module.

Main agent after the merge: the running head settles the volume when
`citableAs` disagrees (five files); `--volumes-dir` makes the comparison
reproducible on a re-load; the 113th to 119th Congresses loaded into the dev
Postgres from the zips (2,149 laws, 55,897 units, 63 s; 34 laws of volume
137 replaced; 11,840 identifiers on 13 levels compared, all agree); a live
poll (2,149 listed, none due, 12 s); the compose stack on :8010 checked on
`/us/pl/118/5/dA/tI/s101`, `/us/pl/118/22/s101` (same served identifier,
text, pages and alternatives as before the load; `law.source` and
`provenance` now PLAW and `gpo-uslm`, and the latest amending law 118-35
carries its date now that it is loaded), `/us/stat/137/112`,
`/laws/118/22` and `/status`; ADRs, README, CLAUDE.md, this entry.

Decisions: ADR-0011 (a PLAW package outranks the volume file), ADR-0012 (what
stays volume-derived: private laws, the 104th to 112th), ADR-0013 (GPO's
identifiers are read; rules-1.0 fills the gaps; the running head wins over a
wrong `citableAs`).

Verified: `make test` 263 passed, 5 deselected, no network; the seven
reports in `docs/verification/`.

## 2026-09-08 — stage 5: the reader, the citation parser, the US Code site integration

Asked: build design stage 5 (sections 3, 4, 5 and 7): the reader at `/app`,
the citation parser behind `GET /api/v1/cite`, and the US Code site's links
to this site.

Main agent first: `citeparse.py` (pure; 125 accepted-forms cases in
`tests/test_citeparse.py`), `api/cite.py` (`GET /api/v1/cite?q=`: parse,
then `Repository.labels`, `stat_page` or `get_comp_unit`; 422, `exists:
false`, `exists: true`; `kind: "usc"` with the US Code site's URL and no
check; 60 requests then 2 a second; `max-age=300`; ETag), `CiteOut`,
`cite_note`, `cite_not_a_citation` and `cite_chapter_not_on_page` in
`params.py`, `POST /labels` answering a `/us/stat/{vol}/{page}` identifier
with the page's documents (`LabelPageOut`), `make cite`, the architecture
test that the parser imports no storage, db, fastapi or sqlalchemy, and
`docs/plans/2026-09-08-reader-contract.md` (every route each reader page
calls and every sentence it prints verbatim). Committed before delegating;
`make test` 408 passed.

Two subagents in worktrees, neither touching `api/`, `storage/`, `db/` or
`params.py`:

- (a) the reader, `frontend/`: Astro 5 with TypeScript and USWDS 3, SSR on
  Node at `/app`, one typed client over `/api/v1`, the pages of the contract
  (`/app/`, `/app/goto`, the enacted unit page shared by `/us/pl`, `/us/pvtl`
  and `/us/act`, `/app/us/sComp`, `/app/us/stat`), the typed USLM renderer
  ported from the US Code site's and adjusted to statutes USLM, the
  reference rule over `/labels`, the "cited by" panel, previous and next
  from the law's table of contents, the API's `Cache-Control` copied; the
  compose `frontend` service and the Caddy `handle /app*` block; `make dev`
  (API and reader), `dev-web`, `test-web`, `test-e2e`. 62 vitest units, 17
  Playwright tests with axe, `astro check` clean.
- (b) the US Code site, branch `statutes-links` in a worktree of
  `../uscode-redesign` (four commits, not pushed): `fetchStatuteLabels`
  (`POST {STATUTES_ORIGIN}/api/v1/labels`, 100 per request, cached five
  minutes, nothing when the origin is unset or the call fails),
  `citedStatuteIdentifiers`, `resolveRef` linking `/us/pl/`, `/us/pvtl/`,
  `/us/act/` and `/us/stat/` refs to this site when `exists: true` with the
  hover label, govinfo for `false` or no answer; the version timeline's law
  chips linked to `/us/pl/{c}/{n}?view=enacted` and to each section
  designator; `pl_sections` on `VersionLawOut`, read at request time from
  the classification rows; `STATUTES_ORIGIN` in `.env.example` and both
  compose files. Verified there: `make test` 869 passed, 2 skipped;
  `make test-web` 517 passed; the CSP needs no change (the labels call is
  server-side; the links are navigations). 13 `astro check` errors
  pre-exist on its `main`.

Main agent after the merge: the compose stack rebuilt with the reader
(`docker compose up -d --build`, the proxy recreated for the new Caddyfile)
and checked on :8010: `/app/us/pl/81/740/s3` (immutable),
`/app/us/act/1950-08-30/ch823/s3` (the alias sentence),
`/app/us/pl/118/22/s101` (the section-number sentence and the amended
sentence naming Public Law 118-35), `/app/us/pl/118/5/dA/tI/s101/a` (the
provision marked `target` inside its section), `/app/us/sComp/83/703/tI/ch1./s1`
(`max-age=300`, immutable with `?through=118-67`), `/app/us/stat/137/112`,
`/app/goto?q=110 Stat. 4196` (404, `no-store`, the note), `/app/goto?q=garbage`
(422, the detail), `/app/goto?q=Pub. L. 81-740, § 3` (307 to the unit),
`/app/goto?q=43 U.S.C. 1701` (307 to the US Code site), and the bare
citation URL redirecting a browser into the reader; the axe spec widened to
one page of each kind (twelve pages, no violations); ADR-0014, 0015, 0016;
README; this entry.

Decisions: ADR-0014 (the reader's stack and what it prints verbatim),
ADR-0015 (the citation parser's forms and failures), ADR-0016 (the
cross-site link rule in both directions).

Verified: `make test` 408 passed, 5 deselected, no Node, no network;
`make test-web` 62 passed; `make test-e2e` over the compose stack 26 passed;
`npx astro check` 0 errors.

## 2026-09-08 — the deployment: the shared box, the edge, the weekly update

Asked: build the deployment of statutes.linkedlegislation.org per
`docs/plans/2026-09-08-deployment-plan.md` (accepted: the US Code site's
`t4g.large`, a second compose project behind one edge Caddy, bots
disallowed, cross-site links allowed) and its counterpart on the US Code
site. Nothing touches AWS until told.

Main agent first: the reader forwards the browser's address on every
server-side call (`CallOptions.clientAddress` in `frontend/src/lib/api.ts`,
`clientAddressOf` in each page, a vitest unit over the header),
`/app/healthz` (200, no API call), `deploy/Caddyfile` with `header_up
X-Forwarded-For {client_ip}` and `trusted_proxies static 10.83.0.0/24` (the
edge subnet; `private_ranges` would trust a workstation peer on the dev
stack), the weekly update's flags (`fetch-statute --if-changed` over the
Hub tree listing, `statute --changed-only` over `source_checks.source_sha256`
with migration `9c1f2b7d3e40`, `citations --from-hub --if-changed` over the
dataset revision; `/status` `citations.checked_at`), `make load-prod`,
`update-prod`, `update-prod-check`, and the reader contract's forwarded
address section. Checked on the compose stack: a forged `X-Forwarded-For`
from the workstation is keyed on the peer, `/app/goto` is keyed on the
browser's address. Committed before delegating.

Two subagents in worktrees:

- (a) this repository's deployment files: `docker-compose.prod.yml` (no
  published ports, ECR images with `build:` fallback, healthchecks,
  `mem_limit` 768m/512m/384m/64m, the proxy on `edge` as
  `statutes-proxy`), `.env.prod.example`, `deploy/edge/` (compose,
  Caddyfile, `up.sh`, README), `docker-compose.edge.yml` (the rehearsal
  override), `deploy/lib.sh`, `provision.sh`, `admin-grant.sh` and its
  bootstrap policy, `bootstrap-box.sh`, `deploy-on-box.sh`,
  `update-sources.sh`, `install-crons.sh`, `watchdog.sh`, `alarms.sh`,
  and the three workflows. `shellcheck`, `actionlint`, `docker compose
  config` and `caddy validate` clean. The rehearsal on this machine: the
  edge on :8020, both dev proxies joined.
- (b) the US Code site's branch `shared-edge` (three commits in
  `../uscode-redesign/.claude/worktrees/shared-edge`, not pushed): the
  proxy without ports on `edge` as `uscode-proxy`, its Caddyfile with the
  same trust rule and `{client_ip}`, the deploy check and watchdog through
  the edge by hostname, `docs/deploy.md` section 9 "Sharing the box",
  ADR-0020 and ADR-0029 amended, `docs/verification/xff.md` with the
  measurement. There: 867 passed 2 skipped; 473 vitest.

Main agent after the merge: the end-to-end rehearsal through the edge
(both hostnames, the bare citation URLs redirecting a browser, robots,
the forged header replaced at the edge, one address drained while another
answers), `.dockerignore` for both images, ADR-0017, ADR-0018, README,
CLAUDE.md, this entry; the rehearsal taken down with both dev stacks left
running.

Decisions: ADR-0017 (two sites, one edge: what is shared, the trusted
subnet, the reader's forwarded address, the cut-over order), ADR-0018
(the weekly update: what each step asks its source, the dump that follows
the data, the two schedules).

Verified: `make test` 419 passed, 5 deselected, no Node, no network;
`make test-web` 68 passed; `make test-e2e` over the edge on :8020 26
passed; `npx astro check` 0 errors; `alembic upgrade head` on the dev
Postgres. Not run: anything against AWS, the box scripts end to end.

Next, with the user's go-ahead: plan section 3 (AWS, once), section 4 (the
box and the cut-over), section 5 (the load), then `STATUTES_ORIGIN` on the
US Code site once `statutes-links` is merged.

## 2026-09-09 — go-live: AWS, the box, the cut-over, the load

Asked: take the site live per `docs/plans/2026-09-09-go-live-prompt.md`,
one section at a time.

Preflight. `AWS_PROFILE=uscode-admin` is the IAM user
`linkedlegislation-deploy`, the ordinary deploy identity; no profile on
the workstation holds IAM, so the IAM step ran from CloudShell under the
user's administrator login. CI on `822bd82` had failed in shellcheck:
Ubuntu's 0.9.0 reports SC2317 on every line of a function invoked only
through `step`; 0.11.0 here does not. Fixed with SC2317 in the two
directives. The box: `i-06b433caacd78fd96`, `t4g.large`, us-east-1a,
Elastic IP `52.1.30.78`, 7.8 GB memory with 2.9 GB available, the US Code
volume 120 GB at 36%; Docker Compose v5.3.1; no `make`.

Section 3, AWS. `admin-grant.sh` (CloudShell): the inline policy
`statutes-backups` on `uscode-site`, the OIDC role
`arn:aws:iam::739065237548:role/statutes-github-deploy`. Its existence
check had swallowed the error text, so an invalid token read as "role
does not exist"; it now prints the error and the identity. `provision.sh`
(CloudShell): the volume `vol-01fbc07d5cab61539`, 40 GB gp3, attached as
`/dev/xvdc`; the bucket with its lifecycle and public-access block; the
two ECR repositories with the ten-tag lifecycle. The A record in zone
`Z007577931KDAIYFR232H`. `deploy/provision-policy.json`, the actions the
deploy identity lacked (S3 bucket, ECR, SNS, Route 53 writes and the IAM
reads), attached as the managed policy `statutes-provision`: at 2,057
bytes it is over the 2,048-byte inline limit for a user. The harness's
permission classifier declined every AWS write and SSM write from this
session; the user ran the AWS writes, and the SSM writes went through a
one-file runner the user allowed.

Section 4, the box. `bootstrap-box.sh` in the user's SSM session, the key
read with `read -rs` so it is in no history: `/dev/nvme2n1` formatted and
mounted by UUID at `/var/lib/statutes`, the clone, `.env` mode 600 with
the eight keys, `/etc/cron.d/statutes`. The cut-over: the US Code `.env`
set to `SITE_ADDRESS=http://uscode.linkedlegislation.org:8000`; the user
merged `shared-edge` (rebased over one PR merged since); its first deploy
failed at `up` with "network edge declared as external, but could not be
found" before touching a container, so the network was created by hand
(`docker network create --subnet 10.83.0.0/24 edge`) and the deploy
dispatched again; it ended at its robots check as its runbook says;
`deploy/edge/up.sh` brought the edge up; the US Code site answered
through it within a minute with a fresh Let's Encrypt certificate. The
fix: `up.sh --network-only` as the cut-over's first step, ADR-0017
decision 6, the plan, the edge README, and the US Code site's
`docs/deploy.md` section 9 (its PR #77). Then `AWS_DEPLOY_ROLE_ARN`,
`deploy.yml` on dispatch: images built and pushed in 2m37s, the box's
deploy from `0a926d5` through the robots check. `alarms.sh`:
`statutes-alerts`, `statutes-site-down`, `statutes-disk-high`; the
CloudWatch agent's `uscode.json` gained `/var/lib/statutes` under `disk`
and was reloaded (`mount_points` shows all three). `make` installed.

Section 5, the load. `make load-prod` detached under `nice`, 06:41 to
07:38 UTC: 137 volumes fetched (2.3 GB), all 137 loaded in 35 minutes
with no error, volumes 7 and 8 empty (the treaty volumes), 137 reports in
`data/verification/`; PLAW 113th to 119th, 2,149 laws in 8 minutes
(1,773 replaced volume-derived, 342 new: the Hub's volume 137 holds 34
laws); citations 1,081,463 rows over 56 titles in 481 s, dataset revision
`a34c462`; classifications 31 files, 144,885 rows; the first COMPS run
397 of 400 packages, three failed (GovInfo 400 on the USLM of
COMPS-17514 and COMPS-10414; COMPS-77777777 carries no identifier). The
database is 2,676 MB. `/status` lists 126 `STATUTE` volumes, not 137:
the count is of volumes with volume-derived laws, and the PLAW load
replaced every public law of volumes 127 to 137 except the private laws
of 132 and 136 (ADR-0011). The first dump:
`s3://statutes-linkedlegislation/db/statutes-2026-09-09.dump`, 621 MiB.
The smoke test passed; Playwright 26 passed after the two 404 cases were
pointed at `/us/stat/999/1` (they had assumed volume 110 absent, true of
the fixture database only). `make update-prod-check`: three checks
written, 137 volumes listed and unchanged, nothing fetched, `stale`
false. The COMPS walk: GovInfo lists newest first and a poll's default
start is the newest date seen, so the plan's repeated `--limit 400`
re-saw the same packages; `--limit` now counts packages fetched, `make
comps-walk` names the start, and the unit `statutes-comps-walk` runs it
hourly until a run fetches nothing (log `logs/comps-walk.log`).

Decisions: none new. ADR-0017 decision 6 amended (the network first).

Verified: `make test` 420 passed, 5 deselected; the smoke test and 26
Playwright tests over the live site; both hostnames through the edge;
the dump in the bucket; the alarms in `INSUFFICIENT_DATA` until the
watchdog and the agent publish. Not done: `STATUTES_ORIGIN` on the US
Code site (`statutes-links` unmerged there); the SNS subscription awaits
the user's confirmation; the remaining worktrees `agent-a09…`, `a8e4…`,
`ad80…`, `ae81…`, `aefd…` are earlier stages' and were left.

## 2026-09-09 — planning: the reader improvements

Asked: plan seven reader changes for later sessions to build on
cost-efficient models: the text of a Statutes at Large page, the law
page's load time and its pages list, a fixed header, a side rail with
the page's panels and the law's contents, top and bottom links,
keyboard shortcuts, and keyword search in the citation box as on the
US Code site.

Measured on the live site: `GET /api/v1/us/pl/117/328` is 4,748,777
bytes in 4.8 s (`text` is the whole law's plain text, 4,548,249
characters, parsed from the 20 MB law XML on every request; `pages`
lists 1,653 rows); `/app/us/pl/117/328` is 565,162 bytes in 4.0 s;
`/us/stat/110/4196` holds Public Law 104-333 with the marker in
section 814. The US Code site's search is the OpenSearch engine
(its ADR-0028, 0031, 0051), not the browser description format; the
box has 8 GB with that site's cluster at a 2 GB heap, so a second
cluster does not fit and the plan shares that one over its network.

Written: `docs/plans/2026-09-09-reader-improvements-plan.md` (six
packages A to F with API shapes, file ownership, tests, ADRs 0019 to
0023, a wave table with a model per package, and a measured
acceptance list) and `2026-09-09-reader-improvements-prompt.md`.

Decisions: recorded in the plan, to be filed as ADRs by the packages.
Nothing built; nothing committed.

## 2026-09-09 — the COMPS walk ends; its failures documented

Asked: read the walk's state on the box after the monitor saw the loaded
count hold at 2,675 for 100 minutes; document the packages that failed to
load; push the held commit.

Found: the unit `statutes-comps-walk` was still active after seven runs.
The seventh saw 2,685 packages, 2,675 already current, 10 fetched and 10
failed, 0 new; the walk's stop rule was "0 fetched" and a failed package
counts as fetched, so it would have retried the same 10 every hour. The
user stopped the unit over SSM. The 10, from their summaries and USLM:
four with no USLM on GovInfo (the `uslm` endpoint answers 400: the Railway
Labor Act, the Consolidated Appropriations Act 2023, two more); five USLM
files of 2 to 7 KB with `meta` and no `main`; and COMPS-77777777, the whole
Public Health Service Act in 13 MB, whose 25,701 identifiers have an empty
law slot (`/us/sComp//tI/s1`) and whose summary names no law. The act is
served title by title under `/us/sComp/78/410`; the bare prefix resolves to
the title XXXII file (marked repealed), since ADR-0007's whole-act rule has
no whole-act file to pick. Left as a follow-up with the walk's stop rule
in the box script.

Written: the README's compilation section, ADR-0007's consequences, the
deployment plan's walk line, a Statute Compilations section in
`docs/verification/README.md`, and the reader's front page, which now
prints the packages loaded against the packages the last check saw and a
sentence for the difference (`Status.checks` added to the reader's types).

Decisions: none new.

## 2026-09-09 — the walk script in the repo, stopping on a run that loaded nothing

Asked: fix the walk's stop rule, in a worktree, as a PR.

Written: `deploy/comps-walk.sh`, the loop the box ran from an ad hoc
`/var/lib/statutes/comps-walk.sh`, now in the repo: `make comps-walk`
(overridable as `WALK_CMD`) every `INTERVAL` seconds, at most `MAX_RUNS`,
each run logged whole, ending on a run whose summary line carries
`ingest.comps.NOTHING_NEW` (`, 0 new, 0 new versions,`). `summary_line`
is the one line `comps poll` prints, extracted so the test can build the
lines the script sees. `tests/test_comps_walk.py` runs the script against
a fake poll: it ends on the first run that loaded nothing and stops at
`MAX_RUNS` otherwise. README, the deployment plan, ADR-0007 and the
Makefile name the script and the `systemd-run` line that starts it.

Decisions: none new; ADR-0007's consequence names the script.
