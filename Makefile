.PHONY: dev dev-api dev-web migrate dev-data dev-up test test-web test-e2e test-slow test-all fixtures verify fetch load-all lint fetch-uscode citations classifications fetch-plaw plaw plaw-poll cite load-prod update-prod update-prod-check

# The API on :8001 and the reader's dev server on :4321, against the compose
# Postgres (:5434 on the host). The reader's Vite proxy sends /api/v1, /health,
# /docs and /openapi.json to API_BASE_URL (default http://localhost:8001).
dev: dev-up migrate
	$(MAKE) --no-print-directory -j2 dev-api dev-web

# The API alone.
dev-api:
	uv run python -m uvicorn main:app --reload --port 8001

# The reader's dev server alone (stage 5; frontend/). API_BASE_URL picks the
# API it reads: the compose stack is API_BASE_URL=http://localhost:8010.
dev-web:
	cd frontend && npm install --no-audit --no-fund && npm run dev

dev-up:
	docker compose up -d db

migrate:
	uv run alembic upgrade head

# What docs/verification/ describes: volumes 64 and 124 from the Hub, loaded,
# with a per-volume report written next to the committed ones.
dev-data: migrate
	uv run python -m ingest statute --volumes 64,124 --report docs/verification

# Every volume on the Hub (1 to 137). Idempotent per volume; re-run to resume.
load-all: migrate
	uv run python -m ingest statute --volumes 1-137 --report docs/verification

fetch:
	uv run python -m ingest fetch-statute 26 64 68 72 116 124 137

# Stage 3: the citation index from the dreamproit/uscode dataset (config
# `current`, three parquet shards under data/uscode), and the classification
# tables mirrored from the US Code site's API. Neither is part of `make test`.
fetch-uscode:
	uv run python -c "from pathlib import Path; from ingest.hub import fetch_uscode_shards; print(fetch_uscode_shards(Path('data/uscode')))"

citations: migrate
	uv run python -m ingest citations --from-hub --report docs/verification

classifications: migrate
	uv run python -m ingest classifications --report docs/verification

# Stage 4: GovInfo PLAW bulk data (public laws with USLM, 113th Congress
# onward), one zip per congress under data/plaw. `plaw` fetches what is missing,
# loads every congress, and writes docs/verification/plaw-{c}.json. Neither is
# part of `make test`.
fetch-plaw:
	uv run python -m ingest plaw fetch 113-119

plaw: migrate
	uv run python -m ingest plaw load 113-119 --report docs/verification

# The poller: the bulk-data listings against what is stored, the zip for a
# congress that is new or mostly due, single files otherwise (ingest/plaw_poll.py).
plaw-poll: migrate
	uv run python -m ingest plaw poll --report docs/verification

# The specification. Runs over SQLite with the committed slices; needs no
# database and no network.
test:
	uv run pytest

# The reader's unit tests: vitest over frontend/src/lib (the renderer, the
# reference rules, the URL helpers, the labels client). Needs Node, not a
# browser, a database or the network. Not part of `make test`.
test-web:
	cd frontend && npm install --no-audit --no-fund && npm test

# The reader's browser tests: Playwright over a running site (BASE_URL,
# default http://localhost:4321; `make dev` or `make dev-web` first).
test-e2e:
	cd frontend && npm install --no-audit --no-fund && npx playwright test

# Parses the whole downloaded volumes under data/statute/xmls (skips when absent).
test-slow:
	uv run pytest -m slow

test-all:
	uv run pytest -m ""

# Regenerate the committed slices from the downloaded volumes and COMPS files.
fixtures:
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-64.xml tests/fixtures/statute-64-slice.xml 1 2 3 29 134 153 357 768 823 1212
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-72.xml tests/fixtures/statute-72-slice.xml 317 322 457 741 829 910
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-124.xml tests/fixtures/statute-124-slice.xml 2 177 230 344
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-137.xml tests/fixtures/statute-137-slice.xml 3 22 34
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-116.xml tests/fixtures/statute-116-slice.xml 259 --plaws 3
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-26.xml tests/fixtures/statute-26-slice.xml 647
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-68.xml tests/fixtures/statute-68-slice.xml 703
	uv run python scripts/extract_comp_fixture.py data/comps/COMPS-1630.xml tests/fixtures/comps/COMPS-1630-slice.xml 8
	uv run python scripts/extract_comp_fixture.py data/comps/COMPS-8755.xml tests/fixtures/comps/COMPS-8755-slice.xml 3
	uv run python scripts/extract_comp_fixture.py data/comps/COMPS-973.xml tests/fixtures/comps/COMPS-973-slice.xml 4
	uv run python scripts/extract_citations_fixture.py data/uscode tests/fixtures/uscode-current-slice.parquet

# Re-derive docs/verification/statute-{n}.json for the loaded volumes.
verify: dev-data

# The compose stack: Postgres, the API, the reader, Caddy on :8010.
up:
	docker compose up --build

# Stage 5: a written citation through the parser (no database) and through the
# running site's `GET /api/v1/cite` (the compose proxy on :8010 by default).
#   make cite Q="Pub. L. 81-740, § 3"        SITE=http://localhost:8001 for `make dev`
SITE ?= http://localhost:8010
cite:
	uv run python -m citeparse "$(Q)"
	curl -sG "$(SITE)/api/v1/cite" --data-urlencode "q=$(Q)" | python3 -m json.tool

# The deployed site (docs/plans/2026-09-08-deployment-plan.md, sections 5 and
# 6). Both run on the box, in the checkout beside docker-compose.prod.yml,
# every step inside the `api` container.
#
#   make load-prod          the whole corpus: the 137 volumes from the Hub
#                           (~1 hour under nice), PLAW 113-119, the citation
#                           index, the classification tables, then the COMPS
#                           walk in slices of 400 packages (repeat `comps poll`
#                           until it reports nothing due). Every step is
#                           idempotent; re-run to resume.
#   make update-prod        the weekly update (deploy/update-sources.sh): each
#                           source asked what changed, loaded only when it did,
#                           a dump to S3 when something was loaded.
#   make update-prod-check  the same, recording the checks and loading nothing.
PROD_COMPOSE = docker compose -f docker-compose.prod.yml
PROD_INGEST = $(PROD_COMPOSE) exec -T api nice -n 10 uv run python -m ingest
load-prod:
	$(PROD_INGEST) fetch-statute 1-137
	$(PROD_INGEST) statute --volumes 1-137 --report data/verification
	$(PROD_INGEST) plaw fetch 113-119
	$(PROD_INGEST) plaw load 113-119 --report data/verification
	$(PROD_INGEST) citations --from-hub --report data/verification
	$(PROD_INGEST) classifications --report data/verification
	$(PROD_INGEST) comps poll --limit 400

# The rest of the first COMPS walk: GovInfo lists newest first, so the walk
# names its start; already-current packages are skipped without a call and
# do not count toward the limit. Once an hour until it reports 0 fetched.
comps-walk:
	$(PROD_INGEST) comps poll --since 1990-01-01 --limit 400

update-prod:
	bash deploy/update-sources.sh

update-prod-check:
	bash deploy/update-sources.sh --check-only
