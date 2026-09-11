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

## 2026-09-09 — the reader improvements: six packages in three waves, and the site-down alert

Asked: build `docs/plans/2026-09-09-reader-improvements-plan.md`, packages
A to F in three waves, each package a subagent in its own worktree on the
model the plan's wave table names; merge into `main` in order; run `make
test`, `make test-web` and `make test-e2e` after each merge; push once per
wave; leave the compilations session's files alone; finish with the
acceptance list measured on the box. Later in the session: the "site down"
mail arrives too often; review and fix it as a separate wave.

Wave 1. A (Sonnet): `Law.xml` is a deferred column, `get_unit` takes
`wanted`, a law's and a node's `text` is empty and their XML is read only
for `format=xml`; the compiled side is left to the compilations session
(ADR-0019). B1 (Opus): `uslmtext.slice_between` and `page_slice`; each
document of `GET /api/v1/us/stat/{vol}/{page}` gains `units` and `text`;
`format=xml` answers one `slice` per law; the slice is cached on `(law.id,
content_hash, page)` at 256 entries; `page_label` moved to `uslmtext.py`.
Measured on the dev database, `/us/stat/136/5000` inside Public Law
117-328 (11.3 MB of XML): 1.41 s first, 0.16 s cached, 0.11 s for the 304,
so no `stat_page_slices` table (ADR-0020). E1 to E3 (Opus for the query
builder and the sync, Sonnet for the CLI, the route, the compose files and
the deploy steps): `storage/search.py`, `storage/searchquery.py` (the scopes
`law:`, `congress:`, `year:`, `vol:`, `kind:`, `view:`, `heading:`;
`simple_query_string` with `default_operator: and`, no fuzziness, the
`<em>` highlighter, facets over `congress`, `kind` and `view`, three
sorts), `ingest/search_sync.py` (one document per unit with text or
heading, plus the compiled sections of each compilation's current version;
the mapping fingerprint; the alias `statutes_units` promoted in one call),
`python -m ingest reindex-search`, `make reindex-search`, `GET
/api/v1/search`, the dev `opensearch` on host port 9201, the deploy's
`--if-changed` step and the weekly update's step (ADR-0023). `law:117-328`
filters `law_identifier`; a compiled document's `_id` carries its COMPS
package; `citation_sort` is the padded volume, the page with its letter
prefix, then `seq`. The dev index built in 60 s: 75,154 enacted and 687
compiled documents.

Wave 2. C (Sonnet, the sticky header and the end links drafted on Haiku):
the header is one row of 56 px at 375, 700 and 1280 (`--sticky-h` 3.5rem);
`Rail.astro` lists the page's panels and the law's contents, bounded to the
open branch above 300 units (checked against Public Law 117-328's
2,155-unit toc); Contents and Pages are closed disclosures; the reader's
first inline script (380 bytes) opens a disclosure a fragment names;
`jsbudget.test.ts` and `docs/js-budgets.json` ported (ADR-0021). B2
(Sonnet): the stat page renders its slice through the USLM renderer with
numeric neighbours, "Begins inside Sec. N — Read section N in full", and
the Documents list reworded. E4 (Sonnet, the syntax page on Haiku):
`/app/search`, `/app/search/syntax`, `/app/goto`'s 422 becomes a 307 to
`/app/search?q=`, the box's placeholder is "Citation or words"; facet links
are edited in TypeScript from the query string, not built from the facet
counts.

Wave 3. D (Sonnet): `lib/shortcuts.ts`, `KeyboardNav.astro` (2,759 bytes)
and `ShortcutsDialog.astro`; every route under `Base.astro` ships 3,139
bytes of inline script and the ceilings rose from 1,000 to 3,500
(ADR-0022); `[` and `]` step the `[id]` children of the rendered section;
`c` reaches the rail when pinned, else `#contents`. F (Haiku): README,
CLAUDE.md's ADR list, this entry; the Haiku draft of the README's chrome
sentences and of this entry was corrected by hand.

The alert wave (Opus). The mail was the US Code site's `uscode-site-down`.
This site's deploy of `dd76171` at 16:36 UTC attached
`statutes-at-large-api-1` to `uscode-redesign_default`, where Docker
registers the service name `api` as an alias; the US Code reader's
`API_BASE_URL=http://api:8001` reached this site's API, its pages answered
404 and 500, and its watchdog restarted its stack six times. `d75ec7e`, a
hotfix pushed between waves, detached the API; `search-relay`
(`alpine/socat:1.8.1.3`, 32 MB, no ports) now carries the cluster
connection and is the only service of this project on that network;
`tests/test_compose_networks.py` asserts the rule. The watchdog publishes
`ApiUp`, `AppUp` and `EdgeUp` beside `SiteUp`, restarts only the half that
failed, restarts nothing when 443 refuses, and reads a probe inside the
deploy's marker window as up; `statutes-site-down` evaluates five of the
last seven minutes with `breaching` and its OK action kept, applied with
`deploy/alarms.sh` (ADR-0024). `--limit-concurrency`, every `mem_limit`,
the restart threshold and the cooldown are unchanged. This site's own alarm
had not fired since the cut-over.

Also: the search route answered 500 on the box with `SEARCH_PASSWORD`
unset; `SearchNotConfigured` is now a 503 with the same sentence. The
first reindex on the box was OOM-killed at 506 MB inside the api
container's 512 MB limit after 434,025 of 434,044 enacted documents: a
500-row batch carried every section's `xml`, and the compiled join carried
the whole compilation's `xml` once per row. The streams now select the
unit's columns by name; measured locally over 75,154 documents, peak RSS
went from 2.29 GB to 222 MB (`80ae003`), and the deploy's `--if-changed`
step finished the box's index. The
vitest run rewrites `docs/verification/js-bytes.json`, which blocked one
merge until the artifact was discarded; it is regenerated and committed
after each merge. A worktree branches from the pushed `main`, not the local
one, so each wave-2 and wave-3 agent merged `main` first.

After the acceptance list, at the user's request: a version and commit
line at the foot of every page in the US Code site's form (`Source:
github.com/aih/statutes-at-large — version 0.1.0, commit <sha>`), the sha
carried into both images as `GIT_COMMIT` by `.github/workflows/deploy.yml`'s
build args and read by `frontend/astro.config.mjs`'s Vite defines and by
`site_version.py`; `GET /health` and `GET /api/v1/status`'s `site` block
answer the same version and commit. README gained "What is live" with the
load numbers and the `GET /api/v1/search` row; the front page's lede and
examples name search and a mid-page Stat. citation; `/docs` names the
search route. `docs/plans/2026-09-09-compilations-prompt.md` holds the
prompt for the compilations session: the compiled side of ADR-0019
(`/us/sComp/74/271` answers 8.4 MB in 4.6 s) and the bare prefix of a
per-title compilation.

Decisions: ADR-0019 to ADR-0024; ADR-0017 decisions 2 and 9 and ADR-0023
decision 2 amended.

Verified after the last merge: `make test` 556 passed, 5 deselected; `make
test-web` 107; `make test-e2e` 65 over `make dev`; `npx astro check` 0
errors on every frontend package; shellcheck on the deploy scripts. Live
after wave 1: `GET /api/v1/us/pl/117/328` 146,610 bytes in 0.39 to 0.45 s
inside the box, about 1 s over TLS from a workstation; `/us/stat/136/5000`
10 ms cached. Live after wave 2: `/app/us/stat/110/4196` prints the slice,
"Begins inside Sec. 814" and the link to `/app/us/pl/104/333/d1/tVIII/s814`
in 0.7 s; `/app/goto?q=wild horses` is a 307 to `/app/search?q=wild+horses`;
the citation form still lands on the section. Not done at the time of
writing: `SEARCH_PASSWORD` on the box and the first reindex (the user's, in
an SSM session); the same alarm damping recommended for the US Code site.

## 2026-09-09 — the compiled side of ADR-0019, and the bare prefix of an act served title by title

Asked: `docs/plans/2026-09-09-compilations-prompt.md`. The compiled answer
stops carrying the whole compilation's text; a bare prefix whose act has
one COMPS file per title and no whole-act file gets a rule.

Found: the Public Health Service Act's per-title files are not where the
walk entry above says. GPO wrote their identifiers with the chapter number,
so 32 titles are under `/us/sComp/78/373` and only the repealed title XXXII
(COMPS-10057) under `/us/sComp/78/410`; `/us/sComp/78/373` answered title
VI, the first file by id as text (`10584` < `8771`), and `/us/sComp/78/410`
its one file. Live: `/us/sComp/74/271` 8,385,144 bytes in 4.46 s,
`/us/sComp/78/373` 77,977 bytes, `/us/sComp/83/703/tI` 540,777 bytes.

Written: `CompVersion.xml` is deferred; `get_comp_unit` takes `wanted`;
`compiled_response` negotiates the format first; the root's and a node's
`text` is empty and their `xml` read only for `format=xml`
(`test_no_text_above_a_section` listens on `before_cursor_execute` and
asserts no statement of a JSON answer selects `comp_versions.xml`).
`_gathered_root_result` answers a prefix with no whole-act file: the files
in title order (`storage.identifiers.title_order`, Roman then Arabic then
the rest; `roman_to_int` moved there from `ingest/identifiers.py`), the
act's name from the first file's display title with its suffix removed
(`act_title`), every file's top-level units as `children` in one query,
`files` on the answer, `versions` empty, the hash a sha256 over the files'
hashes, the note's first and third sentences replaced
(`params.compiled_note`), and `format=xml` a 404 with
`params.no_whole_document`. `_toc` skips a gathered root so a per-title
file's `/comps/{id}` still lists its title node. The fixture database's
`/us/sComp/74/271` (COMPS-8755 alone) is the test case
(`test_the_root_of_an_act_served_title_by_title`); the axe list gained
`/app/us/sComp/74/271`. The reader is unchanged: its root title reads
`compilation.display_title`, which the gathered root sets to the act's
name.

Decisions: ADR-0019 gains a "Compiled" section; ADR-0007 decision 8 and its
decision 1 and walk consequence amended. Candidate (b), a redirect to the
first title's file, was not taken. COMPS-77777777 stays unloadable: the
rule gathers files, it does not repair an empty law slot.

Verified: `make test` 560 passed, 5 deselected; `make test-web` 107; `make
test-e2e` 74 over the dev servers. On the dev database: `/us/sComp/74/271`
2,340 bytes in 19 ms, `/us/sComp/83/703/tI` 4,625 bytes in 19 ms;
`/app/us/sComp/74/271` prints "Social Security Act" and the title II node;
`/app/us/sComp/83/703/tI/ch1./s1` renders as before. Live after the
deploy of `89027bd`, over TLS from a workstation: `/us/sComp/74/271` 5,054
bytes in 0.44 s (from 8,385,144 and 4.46 s); `/us/sComp/83/703/tI` 4,625
bytes in 0.30 s (from 540,777); `/us/sComp/78/373` 21,334 bytes in 0.51 s,
"Public Health Service Act", 32 files, 32 title nodes as children, no
versions; `/us/sComp/78/410` 2,346 bytes, the same name over its one
title; `/us/sComp/78/373?format=xml` the 404 sentence;
`/us/sComp/74/271?format=xml` still the 20 MB whole-act document;
`/app/us/sComp/74/271`, `/app/us/sComp/78/373` and
`/app/us/sComp/83/703/tI/ch1./s1` render, the last with its section
body; `/comps/8771`'s `toc` still its title node. Two things met on the
way: `make dev` from a worktree names its compose project after the
directory and tries a second `db` on 5434, which the shared database
already holds (the never-started `statutes-wt-compiled-db-1` container and
its empty volume are left for the user to remove; the servers were run
with `make -j2 dev-api dev-web`); and `storage/search.py` reads
`SEARCH_PASSWORD` from the process environment only, not `.env`, so the
seven search browser tests answer 503 until the shell exports it.

## 2026-09-10 — search settings from `.env`, and fixed compose project names

Asked: `docs/plans/2026-09-10-dev-environment-prompt.md`. `make dev` and
`make test-e2e` from any checkout, including a worktree, with nothing
exported.

Done:

- `storage/search.py`: `SearchSettings` (pydantic-settings, `env_file=".env"`)
  replaces the module constants and `os.environ.get` calls, and holds
  `DISABLE_SEARCH_SYNC`; `ingest/search_sync.py: _disabled` and
  `ingest/reindex_search.py` read it. `tests/conftest.py` sets
  `storage.search.ENV_FILE = None`; the two "no password" tests set
  `SEARCH_PASSWORD=""`. `tests/test_search_settings.py` is new.
- `docker-compose.yml` is project `statutes-linkedlegislation`,
  `docker-compose.prod.yml` project `statutes-at-large` (the box's existing
  name), `docker-compose.edge.yml` none; `tests/test_compose_networks.py`
  asserts all three.
- ADR-0025; ADR-0023 decision 9 amended; README "Running it", CLAUDE.md
  gotcha 10 and the ADR list, `.env.example`.

Verified: `make test` 569 passed, 5 deselected, with `.env` present and with
it moved aside; `make test-web` 107. From this worktree with `SEARCH_*`,
`DATABASE_URL` and `DISABLE_SEARCH_SYNC` unset in the shell: `docker compose
--dry-run up -d db` and then `make dev` printed `Container
statutes-linkedlegislation-db-1 Running` and created nothing, the migration
ran, `GET /api/v1/search?q=rubber` on :8001 answered 200 with 101 results,
and `make test-e2e` passed 74. `docker ps` shows one `db` and one
`opensearch` for the project and no `statutes-wt-*` container. The same from
a fresh worktree at `a20f96e` with only `.env` copied in: `make dev` printed
the running `db`, the API answered search 200, `make test-e2e` passed 74;
the worktree was removed afterwards.

Live after the deploy of `a20f96e` (pushed 23:22 UTC, `/health` reporting
it within two minutes): `GET /api/v1/search?q=rubber` 200, 445 results,
13,308 bytes in 0.45 s over TLS from a workstation; `/app/search?q=rubber`
200. Not checked: `docker ps` on the box, which would show the containers
still named `statutes-at-large-*` after the project name was pinned.

## 2026-09-10 — XML is a section's representation

Asked: `docs/plans/2026-09-10-root-toc-prompt.md`. The compilation root,
the enacted law and every hierarchy node answer their table of contents for
every format; XML is served for a section and a provision only.

Done:

- `params.serves_xml` (the level is `section`). `unit_response` and
  `compiled_response` answer `format=xml` and an XML `Accept:` above a
  section with the JSON body and headers; `_etag` adds `;xml` only where
  XML is served. `xml_url` is `str | None` on `UnitOut` and `CompUnitOut`,
  null above a section. `params.no_whole_document` is gone; a gathered root
  answers like every other root.
- `storage/postgres.py`: `get_unit` and `get_comp_unit` keep `wanted`; the
  private helpers lost it, and `_law_result`, `_comp_root_result` and both
  hierarchy branches set `xml=""` without reading `Law.xml` or
  `CompVersion.xml`. The columns stay deferred; the stat page slice still
  reads `Law.xml`.
- Tests: `test_no_law_xml_is_read_above_a_section` (new) and
  `test_no_text_above_a_section` (extended to the XML requests) listen on
  `before_cursor_execute`. The `format=xml` assertions on `/us/pl/81/740`,
  `/us/pl/111/344/tI`, `/us/pl/118/22`, `/us/sComp/83/703` and
  `/us/sComp/74/271` expect the JSON answer, byte-equal, with the same
  ETag.
- The reader prints "Source XML" only when `xml_url` is set; `types.ts`
  follows. `fetchUnitXml` (`lib/unitpage.ts`) and `fetchCompUnitXml` (the
  compiled page) were already called for sections only. `section.spec.ts`
  gained "source XML is linked on a section only".
- ADR-0019 gains "XML above a section" and dated notes on its decision 2
  and compiled decision 2; ADR-0001's decision and consequence and ADR-0007
  decision 8's sentence struck through with dated notes; the reader
  contract; README's route tables.

Decision: `format=xml` above a section is a 200 with the JSON body, not a
406 (ADR-0019, "XML above a section", decision 2).

Verified: `make test` 570 passed, 5 deselected; `make test-web` 107; `make
test-e2e` 75 over `make dev`, the axe scan including `/app/us/pl/81/740`
and `/app/us/sComp/74/271`; `npx astro check` 0 errors. On the dev
database: `/us/sComp/74/271?format=xml` 2,308 bytes in 18 ms, byte-equal to
the JSON; `/us/sComp/83/703/tI?format=xml` 4,590 bytes;
`/us/pl/117/328?format=xml` 146,580 bytes in 0.20 s;
`/us/sComp/83/703/tI/ch1./s1?format=xml` and `/us/pl/81/740/s3?format=xml`
start with `<section`. `origin/main` was PR #2's merge commit, with no
file changes; it was merged into the branch so the push fast-forwards.

Live after the deploy of `00f6036` (`/health` reported it 123 s after the
push), over TLS from a workstation: `/us/sComp/74/271?format=xml` 5,022
bytes in 0.30 s (from 20,419,115 and 4.66 s), `application/json`,
byte-equal to the JSON answer with the same `ETag`, `Cache-Control` and
`Vary`; `/us/sComp/83/703/tI?format=xml` 4,590 bytes (from 1,152,624);
`/us/pl/117/328?format=xml` 146,580 bytes in 0.89 s, byte-equal to the
JSON (0.86 s), 2.9 s on the first request after the deploy;
`/us/sComp/78/373?format=xml` 21,302 bytes, the gathered root's JSON;
`/us/sComp/83/703/tI/ch1./s1?format=xml` 1,866 bytes and
`/us/pl/81/740/s3?format=xml` 4,066 bytes, both starting with `<section`.
`/app/us/sComp/83/703/tI/ch1./s1` and `/app/us/pl/81/740/s3` render their
section body with the Source XML link; `/app/us/sComp/74/271`,
`/app/us/pl/117/328` and `/app/us/sComp/78/373` render without one. The
axe spec over `BASE_URL=https://statutes.linkedlegislation.org` passed 16,
`/app/us/pl/81/740` and `/app/us/sComp/74/271` among them.

## 2026-09-10 — a deploy skips a documentation-only change

Asked: why a documentation-only change redeploys; then a gate for it; then
that work lands on a branch as a pull request the user merges. CLAUDE.md
gains "Branches and pull requests". This change is the first on that path,
branch `deploy-docs-gate`.

Found: `deploy.yml` ran on every successful CI run on `main` without
looking at the diff, and both images change on every commit (`COPY . .`
takes `docs/`; `GIT_COMMIT` is a build argument). `/health` reported
`d5d9228`, a `BUILDLOG.md`-only commit, as deployed.

Done: `deploy/deploy-gate.sh <sha> [health-url]` and a `gate` job in
`deploy.yml` ahead of the `deploy` job. Both builds pass the resolved sha as
`GIT_COMMIT` in place of `github.sha`. ADR-0026; the deployment plan (item 5,
section 7), README and CLAUDE.md name the gate.

Decision: ADR-0026.

Verified: `shellcheck deploy/*.sh deploy/edge/*.sh` and `actionlint` clean.
The gate against a `file://` health answer: `00f6036..d5d9228` (1 path) and
`cc57c5e..d5d9228` (5 paths, `docs/adr/` and Markdown at the root) `false`;
`f1d1016..d5d9228` `true` on `frontend/src/components/UnitPage.astro`; the
same sha `false`; a deployed commit newer than the new one, `commit:
unknown`, a sha not in the checkout and a refused connection `true`.
Against the live `/health` (`d5d9228`) for `d5d9228`: `false`. Not yet run
in Actions.

## 2026-09-11 — Contents open, a lone section shown, small caps, the note's source

Asked: remove worktrees that are not in use; start the Contents disclosure
open; show a law's section when the contents are one section (Public Law
104-33); render `smallCaps` headings in small caps and a centered heading on
its own line (Public Law 98-181 § 804); say in the note where the XML came
from.

Found: `statutes-wt-compiled` was clean and detached at `origin/main`, with no
unmerged branch. Its `.env` was the only copy (the main checkout had none) and
was copied to the main checkout before the worktree was removed. The Hub's
`STATUTE-51.xml` has the sha256 of the file GovInfo serves at
`/packages/STATUTE-51/uslm`. `processedBy` is `Digitization Vendor` through
volume 116 and `GPO Locator to USLM Converter` from volume 117 and in the PLAW
files. The § 804 h1 was lower case because the API's `heading` carries no
class; the quoted section's heading was `display: inline`.

Done: `details#contents` opens by default; `onlySection` and the
`#text.section-body--whole` article; `titleClass` for the h1; a block
`.uslm-heading.centered`; `source_sentence` at the end of `enacted_note`.

Decision: ADR-0027.

Verified: `uv run pytest` 573 passed; `vitest` 112 passed (with the new
`toc.test.ts` and `titleClass` cases); `astro check` 0 errors. The reader run
locally against the production API: `/app/us/pl/104/33` opens Contents and
renders section 1; `/app/us/pl/98/181/tI/chI/tVIII/s804` has the h1 heading
in `small-caps` and the quoted heading as a block; `/app/us/pl/118/22` opens
Contents with no `#text`. `section.spec.ts` and `chrome.spec.ts` over that
local reader: 23 passed; the 118-3 test's note assertion needs this API
change deployed, or the dev stack.
