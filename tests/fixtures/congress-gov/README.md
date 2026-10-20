# Congress.gov API listing

`law-119-pub.json` is hand-written in the shape of
`GET https://api.congress.gov/v3/law/119/pub?format=json` (the `bills` list and
`pagination`; documented at https://api.congress.gov/). It is not a capture:
only the Public Law 119-1 entry (S. 5, the Laken Riley Act) is a real law, and
it is the one loaded from `tests/fixtures/plaw/PLAW-119publ1.xml`. The entries
for 119-119, 119-120 and the private law are placeholders with made-up bill
numbers, for `tests/test_plaw_pending.py`.

A live response checked on 2026-10-19 has the same keys, plus a top-level
`request` and a per-bill `updateDateIncludingText`.
