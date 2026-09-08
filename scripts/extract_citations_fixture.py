"""Cut the citation-index test fixture from the `dreamproit/uscode` shards.

    uv run python scripts/extract_citations_fixture.py data/uscode tests/fixtures/uscode-current-slice.parquet

Rows are copied verbatim, every column, into one parquet file. The rule:

  * every US Code section whose source credit cites one of the laws in the
    committed volume slices (`LAWS` below, by every identifier the Code writes
    them under), at most `CAP` per law in dataset order;
  * up to `NOTE_CAP` sections that cite the law anywhere else, when the source
    credits cite it nowhere (Public Law 81-740 lives in notes only);
  * the sections named in `ALWAYS`: 16 U.S.C. § 45f (the US Code site's
    worked example) and 16 U.S.C. § 1, whose note cites
    `/us/pl/104/333/dI/tVIII/s814/e/1`, the design's `cited-by` example.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

LAWS = {
    "/us/pl/81/740": ["/us/pl/81/740", "/us/act/1950-08-30/ch823"],
    "/us/pl/81/910": ["/us/pl/81/910", "/us/act/1951-01-06/ch1212"],
    "/us/pl/83/703": ["/us/pl/83/703", "/us/act/1954-08-30/ch1073"],
    "/us/pl/85/910": ["/us/pl/85/910"],
    "/us/pl/111/344": ["/us/pl/111/344"],
    "/us/pl/118/22": ["/us/pl/118/22"],
    "/us/pl/118/34": ["/us/pl/118/34"],
    "/us/act/1890-07-02/ch647": ["/us/act/1890-07-02/ch647"],
    "/us/pl/104/333": ["/us/pl/104/333/dI/tVIII/s814", "/us/pl/104/333/s814"],
}
CAP = 8
NOTE_CAP = 3
ALWAYS = {"/us/usc/t16/s45f", "/us/usc/t16/s1"}
_CREDIT = re.compile(r"<sourceCredit.*?</sourceCredit>", re.S)


def _cites(text: str, forms: list[str]) -> bool:
    return any(f'href="{form}"' in text or f'href="{form}/' in text for form in forms)


def main(source: Path, target: Path) -> int:
    shards = sorted(source.glob("train-*.parquet")) or sorted((source / "current").glob("train-*.parquet"))
    if not shards:
        print(f"no shards under {source}", file=sys.stderr)
        return 2
    credit_hits: dict[str, list[int]] = {law: [] for law in LAWS}
    note_hits: dict[str, list[int]] = {law: [] for law in LAWS}
    chosen: list[tuple[int, int, int]] = []  # (shard, row group, row)
    keep: set[tuple[int, int, int]] = set()
    for shard_index, shard in enumerate(shards):
        parquet = pq.ParquetFile(shard)
        for group in range(parquet.metadata.num_row_groups):
            table = parquet.read_row_group(group, columns=["identifier", "xml"])
            for row, (identifier, xml) in enumerate(zip(table["identifier"].to_pylist(), table["xml"].to_pylist())):
                key = (shard_index, group, row)
                if identifier in ALWAYS:
                    keep.add(key)
                match = _CREDIT.search(xml)
                credit = match.group(0) if match else ""
                for law, forms in LAWS.items():
                    if _cites(credit, forms):
                        if len(credit_hits[law]) < CAP:
                            credit_hits[law].append(key)
                            keep.add(key)
                    elif _cites(xml, forms) and len(note_hits[law]) < NOTE_CAP:
                        note_hits[law].append(key)
    for law in LAWS:
        if not credit_hits[law]:
            keep.update(note_hits[law])
    tables: list[pa.Table] = []
    for shard_index, shard in enumerate(shards):
        parquet = pq.ParquetFile(shard)
        for group in range(parquet.metadata.num_row_groups):
            rows = sorted(r for s, g, r in keep if s == shard_index and g == group)
            if rows:
                tables.append(parquet.read_row_group(group).take(pa.array(rows)))
    out = pa.concat_tables(tables)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(out, target, compression="zstd")
    print(f"{out.num_rows} rows → {target} ({target.stat().st_size // 1024} KB)")
    for law in LAWS:
        print(f"  {law}: {len(credit_hits[law])} by source credit, {len(note_hits[law]) if not credit_hits[law] else 0} by note")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
