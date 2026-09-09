/**
 * The API's response shapes, mirrored from `api/schemas.py`,
 * `api/comps_schemas.py` and `api/cite.py`. Only the fields the reader reads
 * are typed; the wire carries more.
 */

// ------------------------------------------------------------------- laws

export interface LawSource {
  collection: string;
  package: string;
  granule: string | null;
}

export interface Law {
  identifier: string;
  kind: string;
  congress: number | null;
  number: number | null;
  chapter: number | null;
  label: string;
  aliases: string[];
  short_titles: string[];
  official_title: string | null;
  doc_type: string | null;
  enacted: string | null;
  citation: string | null;
  source: LawSource;
}

// --------------------------------------------------------------- currency

export interface Latest {
  pl: string | null;
  identifier: string;
  label: string;
  enacted: string | null;
}

export interface Amended {
  status: "known_amended" | "no_record" | "unknown";
  latest: Latest | null;
  evidence: string[];
}

export interface EnactedCurrency {
  kind: "as_enacted";
  date: string | null;
  amended: Amended;
}

export interface CurrentThrough {
  pl: string | null;
  enacted: string | null;
}

export interface CompiledCurrency {
  kind: "compiled";
  current_through: CurrentThrough;
  fetched: string | null;
  govinfo_last_modified: string | null;
}

// ------------------------------------------------------------------ units

export interface Alternative {
  view: string;
  identifier?: string | null;
  identifiers?: string[] | null;
  current_through?: CurrentThrough | null;
  url: string;
}

export interface Provenance {
  text: string;
  identifiers: string;
  sha256: string;
}

export interface Page {
  page: string;
  pdf: string;
}

export interface Ancestor {
  identifier: string;
  level: string;
  num: string | null;
  heading: string | null;
}

export interface TocEntry {
  identifier: string;
  level: string;
  num: string | null;
  heading: string | null;
  is_section: boolean;
}

export interface Provision {
  identifier: string;
  found: boolean;
  xml: string | null;
  text: string | null;
}

/** `UnitOut`: the enacted view of a law, a hierarchy node, or a section. */
export interface Unit {
  identifier: string;
  served_identifier: string;
  view: "enacted";
  resolution: string;
  law: Law;
  level: string;
  num: string | null;
  heading: string | null;
  currency: EnactedCurrency;
  alternatives: Alternative[];
  note: string;
  provenance: Provenance;
  pages: Page[];
  text: string;
  xml_url: string;
  ancestors: Ancestor[];
  children: TocEntry[];
  provision: Provision | null;
  occurrences: number;
}

// ------------------------------------------------------------ law summary

export interface Compilation {
  file_id: string;
  package_id: string;
  identifier_prefix: string;
  display_title: string | null;
  current_through: CurrentThrough | null;
}

export interface VolumeSource {
  package: string;
  loaded: boolean;
  govinfo: string | null;
}

export interface PlawSource {
  package: string | null;
  uslm: boolean;
  loaded: boolean;
  govinfo: string | null;
}

export interface LawSources {
  served_from: string;
  package: string;
  identifiers: string;
  volume: VolumeSource;
  plaw: PlawSource;
}

/** `LawSummaryOut`: `/api/v1/laws/{c}/{n}`. */
export interface LawSummary {
  law: Law;
  toc: TocEntry[];
  section_count: number;
  compilations: Compilation[];
  sources: LawSources;
}

// ------------------------------------------------------------- stat pages

export interface StatPageDocument {
  identifier: string;
  kind: string;
  title: string | null;
  label: string;
  citation: string | null;
  enacted: string | null;
  starts_here: boolean;
  unit_on_page: string | null;
}

/** `StatPageOut`: `/api/v1/us/stat/{volume}/{page}`. */
export interface StatPage {
  page: string;
  identifier: string;
  volume: number;
  documents: StatPageDocument[];
  pdf: string;
}

// ----------------------------------------------------------------- labels

export interface LabelCurrency {
  kind: "as_enacted";
  date: string | null;
  amended: Amended;
}

/** `LabelFoundOut` for a law or a unit of one. */
export interface LabelUnit {
  exists: true;
  served_identifier: string;
  resolution: string;
  num: string | null;
  heading: string | null;
  level: string;
  kind: string;
  law_identifier: string;
  law_label: string;
  currency: LabelCurrency;
}

export interface LabelPageDocument {
  identifier: string;
  label: string;
  kind: string;
  starts_here: boolean;
}

/** The labels answer for a Statutes at Large page (`level: "page"`). */
export interface LabelPage {
  exists: true;
  served_identifier: string;
  resolution: string;
  num: string | null;
  heading: string | null;
  level: "page";
  kind: "stat";
  volume: number;
  page: string;
  documents: LabelPageDocument[];
  pdf: string;
}

export interface LabelMissing {
  exists: false;
}

export type Label = LabelUnit | LabelPage | LabelMissing;

/** What `POST /api/v1/labels` answers, keyed by the identifier asked for. */
export type Labels = Record<string, Label>;

// ----------------------------------------------------------------- status

export interface CollectionStatus {
  packages_loaded: number;
  latest_package: string | null;
  latest_loaded_at: string | null;
  laws: number;
  units: number;
  volumes: number[];
  congresses: number[];
  laws_by_congress: Record<string, number>;
}

export interface CitationsStatus {
  rows: number;
  citing_sections: number;
  titles: number;
  release_labels: [string, number][];
  loaded_at: string | null;
  /** When the dataset was last asked about, reloaded or not. */
  checked_at: string | null;
  dataset_revision: string | null;
}

export interface ClassificationsStatus {
  rows: number;
  congresses: number[];
}

/** `StatusOut`, the fields the front page shows. */
/** `SourceCheckOut`: the last poll of a collection's source. */
export interface SourceCheck {
  checked_at: string;
  ok: boolean;
  newest_package: string | null;
  newest_last_modified: string | null;
  packages_seen: number | null;
  new_packages: string[];
  error: string | null;
  stale: boolean;
}

export interface Status {
  collections: Record<string, CollectionStatus>;
  checks: Record<string, SourceCheck | null>;
  stale: boolean;
  citations: CitationsStatus;
  classifications: ClassificationsStatus;
}

// --------------------------------------------------------------- cited-by

export interface CitedRef {
  href: string;
  context: string;
  note_topic: string | null;
  date: string | null;
}

export interface CitingSection {
  identifier: string;
  citation: string | null;
  heading: string | null;
  release_label: string;
  url: string;
  refs: CitedRef[];
}

/** `CitedByOut`: `/api/v1/cited-by?identifier=`. */
export interface CitedBy {
  identifier: string;
  law_identifier: string;
  law: Law | null;
  aliases: string[];
  section_num: string | null;
  below: string | null;
  contexts: Record<string, number>;
  total: number;
  limit: number;
  offset: number;
  release_labels: string[];
  sections: CitingSection[];
  note: string;
}

// ------------------------------------------------------------------- cite

/** `GET /api/v1/cite?q=`, a 200. A 422 arrives as `ApiError`. */
export interface Cite {
  query: string;
  kind: string;
  identifier: string;
  section_identifier: string | null;
  law_identifier: string | null;
  label: string;
  exists: boolean | null;
  served_identifier: string | null;
  resolution: string | null;
  level: string | null;
  num: string | null;
  heading: string | null;
  law_label: string | null;
  url: string | null;
  note: string;
  message: string | null;
}

// --------------------------------------------------------------- compiled

export interface CompVersion {
  current_through: CurrentThrough;
  fetched: string | null;
  govinfo_last_modified: string | null;
  is_current: boolean;
  url: string;
}

export interface CompUnitRef {
  identifier: string;
  level: string;
  num: string | null;
  heading: string | null;
  is_section: boolean;
}

export interface CompCompilation {
  file_id: string;
  package_id: string;
  display_title: string | null;
  short_titles: string[];
  identifier_prefix: string;
  law_identifier: string | null;
  partial_of: string | null;
  govinfo_details: string;
}

export interface CompLaw {
  congress: number | null;
  number: number | null;
  identifier: string | null;
  loaded: boolean;
}

/** `CompUnitOut`: the compiled view. */
export interface CompUnit {
  identifier: string;
  served_identifier: string;
  view: "compiled";
  resolution: string;
  compilation: CompCompilation;
  law: CompLaw;
  currency: CompiledCurrency;
  versions: CompVersion[];
  alternatives: Alternative[];
  note: string;
  provenance: Provenance;
  usc_refs: string[];
  text: string;
  xml_url: string;
  level: string;
  num: string | null;
  heading: string | null;
  section_num: string | null;
  ancestors: CompUnitRef[];
  children: CompUnitRef[];
  provision: Provision | null;
}

// ------------------------------------------------------------------ search

/** One value a facet link can add or remove, with its count over the whole
 * result set (not the page). */
export interface SearchFacetValue {
  value: string;
  count: number;
}

/** `SearchFacets`: counts over `congress`, `kind` and `view`. */
export interface SearchFacets {
  congress: SearchFacetValue[];
  kind: SearchFacetValue[];
  view: SearchFacetValue[];
}

/**
 * `SearchResult`: one row (`api/search.py`).
 *
 * `heading` is not highlighted: the highlighter runs over `heading` too, but
 * `_result_of` reads only `highlight.text` into `snippets`, so a result's
 * heading and `num` print plain and only the body snippets carry `<em>`.
 */
export interface SearchResultItem {
  identifier: string;
  law_identifier: string | null;
  law_label: string | null;
  level: string | null;
  num: string | null;
  heading: string | null;
  snippets: string[];
  enacted: string | null;
  citation: string | null;
  view: string;
  comp_prefix: string | null;
  url: string;
}

/** `SearchResponse`: `GET /api/v1/search`. */
export interface SearchResponse {
  results: SearchResultItem[];
  total: number;
  facets: SearchFacets;
  note: string;
}

// ------------------------------------------------------------------- pages

/** One breadcrumb or one navigation link the pages build. */
export interface Link {
  href: string;
  label: string;
}
