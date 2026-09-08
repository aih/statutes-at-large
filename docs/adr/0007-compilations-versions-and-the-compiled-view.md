# ADR-0007: Compilations: one file per package, versions by content, the compiled view by counterpart

Date: 2026-09-07. Status: accepted. Implements design sections 4 to 6 for
`COMPS`; records where the implementation settles what the design leaves open.

## Decisions

1. **A compilation is one GovInfo package** (`comps.file_id` = `meta/property
   [@role="fileId"]`, `package_id` = `COMPS-{n}`). Acts split into one file per
   title (the Social Security Act) are several `comps` rows sharing one
   `identifier_prefix` (`/us/sComp/74/271`); `partial_of` carries the title
   designator. A `/us/sComp/…` request is resolved across every current version
   under the prefix, and the section identifiers tell the files apart. The
   compilation root (`/us/sComp/74/271` with no path) answers from the whole-act
   file when one exists, else the first file by id.

2. **A version is a content hash.** `load_comp` inserts a `comp_versions` row
   when the document's sha256 is new and marks the earlier rows not current;
   the same hash is `unchanged` and touches nothing. `currentThroughPublicLaw`
   is inside the hashed text, so "same hash, different law" cannot occur; if it
   did, the row is relabelled and reported. `?through=118-67` selects the stored
   version with that `current_through_pl`; a `through` that names no stored
   version is a 404 that says so.

3. **The law link is by alias or by (congress, chapter).** `/us/sComp/{c}/{n}`
   names a public law, or a chapter before 1901 (`/us/sComp/51/647` is the
   Sherman Act). `Comp.law_id` is set at load when the law exists;
   `Repository.compilations_for_law` also matches on the numbers, so the link
   holds whichever side loads first.

4. **Alternatives are matched by section number.** The compiled counterpart of
   an enacted section is the compilation's section with the same number under
   the same law (`compiled_counterparts`), and the reverse
   (`enacted_counterpart`). Hierarchy differs between the two sources (`ch1.`
   with a period in the compilation, `tI/ch1` or nothing in the volume), so the
   number is the only stable join. A hierarchy node of a compilation offers the
   enacted law itself. The codified alternative is the `/us/usc/…` reference in
   the compilation's `editorialNote[@role="uscRef"]`; an enacted section with
   no compilation has none until design stage 3 builds the citation index.

5. **`view=compiled` on an enacted identifier serves the counterpart.**
   `/us/pl/83/703/s1?view=compiled` answers with the compiled section the
   alternatives name, in the compiled response shape, with `identifier` the
   compiled form and the note saying which enacted unit was asked for. With no
   counterpart it is a 404 whose body carries the alternatives the enacted unit
   does have (design section 4).

6. **Duplicate section identifiers inside one compilation are not units.**
   COMPS-8755 numbers two sections `215`; `comp_units` has no `occurrence`
   column, the first is the unit and the second stays in the document XML,
   counted in the load report. Adding `occurrence` (as `units` has) is the
   change if a second occurrence must be addressable.

7. **A poll that completed is `ok`.** `source_checks.ok` is false only when the
   collection walk itself failed; packages that failed to load are counted in
   the report and summarised in `error`. A walk that raised is recorded and
   re-raised.

## Consequences

- `Cache-Control` is `immutable` for a compiled unit only when `through=` was
  given and matched (params.cache_control); an unpinned compiled unit is
  `max-age=300`, since a poll can replace it.
- The Atomic Energy Act's compiled sections (`/us/sComp/83/703/tI/ch1./s1`)
  have the amending section `/us/pl/83/703/s1` as their enacted counterpart
  (ADR-0006).
- Live on 2026-09-07: COMPS-1630, 973, 3055, 8755 loaded from the API, then a
  poll since 2026-09-04 walked 3 packages and loaded 2 new ones.
