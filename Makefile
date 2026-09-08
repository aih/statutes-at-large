.PHONY: dev migrate dev-data dev-up test test-slow test-all fixtures verify fetch load-all lint fetch-uscode citations classifications

# The API alone on :8001 against the compose Postgres (:5434 on the host).
dev: dev-up migrate
	uv run python -m uvicorn main:app --reload --port 8001

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

# The specification. Runs over SQLite with the committed slices; needs no
# database and no network.
test:
	uv run pytest

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
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-137.xml tests/fixtures/statute-137-slice.xml 22 34
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-116.xml tests/fixtures/statute-116-slice.xml 259 --plaws 3
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-26.xml tests/fixtures/statute-26-slice.xml 647
	uv run python scripts/extract_fixture.py data/statute/xmls/STATUTE-68.xml tests/fixtures/statute-68-slice.xml 703
	uv run python scripts/extract_comp_fixture.py data/comps/COMPS-1630.xml tests/fixtures/comps/COMPS-1630-slice.xml 8
	uv run python scripts/extract_comp_fixture.py data/comps/COMPS-8755.xml tests/fixtures/comps/COMPS-8755-slice.xml 3
	uv run python scripts/extract_comp_fixture.py data/comps/COMPS-973.xml tests/fixtures/comps/COMPS-973-slice.xml 4
	uv run python scripts/extract_citations_fixture.py data/uscode tests/fixtures/uscode-current-slice.parquet

# Re-derive docs/verification/statute-{n}.json for the loaded volumes.
verify: dev-data

up:
	docker compose up --build
