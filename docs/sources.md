# Sources

Where the text on statutes.linkedlegislation.org comes from, by source. The
reader prints the same account at `/app/sources`
(`frontend/src/pages/sources.astro`).

## Statutes at Large, volumes 1 to 116 (1789 to 2002)

The XML is GPO's USLM for the volume, GovInfo package `STATUTE-{n}`
(`https://api.govinfo.gov/packages/STATUTE-{n}/uslm`). Every law in these
volumes has `meta/processedBy` `Digitization Vendor`. `STATUTE-26.xml`
(`tests/fixtures/statute-26-slice.xml`) has `processedDate` 2026-02-21.

The page images come from two digitization efforts, as GovInfo's
[Statutes at Large help page](https://www.govinfo.gov/help/statute) describes
them: volumes 1 to 64 through digitization led by GPO, with the Library of
Congress ([GPO press release](https://www.gpo.gov/who-we-are/news-media/news-and-press-releases/gpo-makes-available-new-statutes-at-large-dating-back-to-1789));
volumes 65 to 116 through digital imaging on behalf of the Library of
Congress. GPO's digitization vendor read the text from the images and marked
it up in USLM. GovInfo released the USLM in batches:

| GovInfo release | Volumes |
|---|---|
| [June 2025](https://www.govinfo.gov/features/june-2025-release-notes) | 40–43, 45–50, 105, 109 |
| [September 2025](https://www.govinfo.gov/features/september-2025-release-notes) | 94–104, 106 |
| [December 2025](https://www.govinfo.gov/features/december-2025-release-notes) | 29–35, 37–39, 44, 80–93 |
| [March 2026](https://www.govinfo.gov/features/march-2026-release-notes) | 1–28, 36, 64–79 (the notes' list says 19–28; their text says 1–28) |

The releases not listed hold the remaining volumes. Neither GPO nor GovInfo
names the vendor, the OCR engine, or an accuracy figure, and nothing in this
repository's history records them.

The text keeps the vendor's OCR errors. Ones the loader meets:

- Law numbers in marginal notes misread (`835` for `535`), 46 in volume 64
  (ADR-0003).
- `Private Lavr` and `Private law` for `Private Law` (CLAUDE.md, gotcha 2).
- Approval dates such as `1110-04-16` (32 Stat. 1337) and years `1007`, `1807`
  and `1900` in volume 34 (ADR-0036).

## Statutes at Large, volumes 117 to 137 (2003 to 2023)

GPO's USLM from GovInfo package `STATUTE-{n}`, `processedBy` `GPO Locator to
USLM Converter {version}`: converted from GPO's typesetting (locator) files,
with no OCR. The Hub's `STATUTE-137.xml` holds 34 public laws. Volumes 68A and
70A have no USLM or PDF package file on GovInfo and are not served
(ADR-0035).

## The Hub mirror

The loader reads the volume files from the Hugging Face dataset
[`dreamproit/us-statutes-at-large`](https://huggingface.co/datasets/dreamproit/us-statutes-at-large)
(`xmls/STATUTE-{n}.xml`, `ingest/hub.py`), which holds GovInfo's files as
GovInfo serves them, with their sha256 in `metadata.jsonl`. `STATUTE-51.xml`
fetched from GovInfo has the sha256 the dataset records (`7511d02e…`,
ADR-0027). The weekly update compares the dataset's tree listing with the
files on disk and reloads a volume that changed (ADR-0018).

The dataset also holds each volume's PDF. Its card names the
`statute-pdf-to-xml` project, which converts the PDFs to USLM with Docling and
benchmarks the result against GPO's XML. That project's output is not served
here (design stage 6, ADR-0012).

## Public laws from PLAW (113th Congress on)

GPO's USLM from the GovInfo bulk-data public-law files (`PLAW-{c}publ{n}.xml`),
`processedBy` `GPO Locator to USLM Converter`, with GPO's identifiers. A PLAW
file replaces the volume-derived copy of the same law (ADR-0011). Private
laws and laws before the 113th Congress come from the volumes (ADR-0012).

## Statute Compilations

GovInfo's `COMPS` packages, the compilations the House Office of the
Legislative Counsel maintains, in USLM (ADR-0007).

## Citation index and classification tables

The citation index is the `dreamproit/uscode` dataset's `current` config, the
US Code's source credits, notes and text (ADR-0008). The classification tables
are mirrored through the US Code site (ADR-0009).

## What this site changes

The stored XML is GPO's text with `identifier` attributes added. The volume
USLM carries none; the loader assigns them by `rules-1.0`
(`ingest/identifiers.py`, ADR-0013). `provenance` on every response gives the
text's source (`gpo-uslm`), the identifiers' source (`rules-1.0`, `gpo-uslm`
or `gpo-uslm+rules-1.0`) and the sha256. The last sentence of an enacted
unit's `note` names the GovInfo package and the converter (`params.py:
source_sentence`, ADR-0027). For `/us/pl/81/740/s3`:

> The text is from GovInfo package STATUTE-64, converted to USLM from the
> scanned volume by GPO's digitization vendor; the identifiers below the law
> are assigned here by rule (rules-1.0).

This site runs no OCR and corrects no text.
