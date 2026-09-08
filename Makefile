.PHONY: dev dev-api dev-web migrate dev-data dev-up test test-web test-e2e test-slow test-all fixtures verify fetch load-all lint fetch-uscode citations classifications fetch-plaw plaw plaw-poll cite

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
