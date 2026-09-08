# ADR-0005: A volume load keeps public laws, private laws, and joint resolutions

Date: 2026-09-07. Status: accepted. Narrows design section 6 (`laws.kind`
includes `res`).

## Context

A GovInfo volume file holds every document of the volume: `pLaw` components
(acts and joint resolutions, public and private), `resolution` components
(concurrent resolutions), `presidentialDoc` components (proclamations,
treaties, agreements), and part prefaces. The identifiers this site serves
(`/us/pl`, `/us/pvtl`, `/us/act`, `/us/stat`) name laws and pages.

## Decision

The loader stores `pLaw` components only. Joint resolutions are laws with a
number (or a chapter) and are stored as such, with `doc_type = "Joint
Resolution"`. Concurrent resolutions and presidential documents are counted in
the load report under `skipped_components` and not stored, so `/us/stat/{vol}/{page}`
does not list them.

## Consequences

- `laws.kind` takes `pl`, `pvtl`, `act`; `res` is reserved.
- Vol 64: 60 concurrent resolutions and 76 presidential documents skipped;
  vol 124: 38 and 172; vol 137: 6 and 183.
- A page that carries only a proclamation answers 404 on `/us/stat/`.
