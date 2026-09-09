/**
 * The enacted unit page's data, loaded once for `/app/us/pl/…`,
 * `/app/us/pvtl/…` and `/app/us/act/…`. The route page calls `loadUnitPage`
 * in its frontmatter and `applyResponse` before rendering, so the status and
 * `Cache-Control` are set before the response starts.
 */

import { ApiError, type CallOptions, fetchCitedBy, fetchLabels, fetchLawSummary, fetchUnit, fetchUnitXml } from "./api";
import { NO_STORE, copiedCacheControl } from "./cache";
import { citedIdentifiers } from "./refs";
import { sectionNeighbors } from "./toc";
import type { CitedBy, LawSummary, Link, TocEntry, Unit } from "./types";
import { hrefs, parseFragment, render } from "./uslm";

export interface Failure {
  status: number;
  detail: string;
  retryAfter: string | null;
}

export interface UnitPageModel {
  identifier: string;
  unit: Unit | null;
  failure: Failure | null;
  cacheControl: string | null;
  /** `/laws/{c}/{n}`, for a public law's law page and section page. */
  summary: LawSummary | null;
  /** The cited-by panel; null when the call failed or answered 404. */
  citedBy: CitedBy | null;
  /** The rendered section; null on a hierarchy node, a law, or a failed XML call. */
  sectionHtml: string | null;
  neighbors: { previous: Link | null; next: Link | null };
  /** A private law's or an act's nearest ancestor's `children` — the rail's
   * "In this law" list on a section that has no `/laws/{c}/{n}` toc. Empty
   * for a public law's section, where the rail uses the law summary's `toc`
   * instead. */
  parentChildren: TocEntry[];
}

export function describeFailure(error: unknown): Failure {
  if (error instanceof ApiError) {
    return { status: error.status, detail: error.detail, retryAfter: error.retryAfter };
  }
  return { status: 502, detail: `The API did not answer: ${(error as Error).message}`, retryAfter: null };
}

/** Sets the status and the headers on the page's response. */
export function applyResponse(
  response: { status?: number; headers: Headers },
  page: { failure: Failure | null; cacheControl: string | null },
): void {
  if (page.failure) {
    response.status = page.failure.status;
    response.headers.set("Cache-Control", NO_STORE);
    if (page.failure.retryAfter) response.headers.set("Retry-After", page.failure.retryAfter);
  } else {
    response.headers.set("Cache-Control", copiedCacheControl(page.cacheControl));
  }
}

/** `options.clientAddress` is the browser's address, forwarded on every call. */
export async function loadUnitPage(identifier: string, options: CallOptions = {}): Promise<UnitPageModel> {
  const model: UnitPageModel = {
    identifier,
    unit: null,
    failure: null,
    cacheControl: null,
    summary: null,
    citedBy: null,
    sectionHtml: null,
    neighbors: { previous: null, next: null },
    parentChildren: [],
  };

  let unit: Unit;
  try {
    const answer = await fetchUnit(identifier, options);
    unit = answer.body;
    model.unit = unit;
    model.cacheControl = answer.cacheControl;
  } catch (error) {
    model.failure = describeFailure(error);
    return model;
  }

  const isLaw = unit.level === "law";
  const isSection = unit.level === "section";
  const law = unit.law;
  const isPublicLaw = law.kind === "pl" && law.congress != null && law.number != null;

  // A private law or an act has no `/laws/{c}/{n}`; its section's neighbours
  // come from the nearest ancestor's children, or the law's.
  const parentIdentifier =
    unit.ancestors.length > 0 ? unit.ancestors[unit.ancestors.length - 1].identifier : law.identifier;

  const [summary, citedBy, xml, parentChildren] = await Promise.all([
    isPublicLaw && (isLaw || isSection)
      ? fetchLawSummary(law.congress!, law.number!, options).catch(() => null)
      : Promise.resolve(null),
    isLaw || isSection ? fetchCitedBy(unit.served_identifier, 20, options) : Promise.resolve(null),
    isSection ? fetchUnitXml(unit.served_identifier, options).catch(() => null) : Promise.resolve(null),
    isSection && !isPublicLaw
      ? fetchUnit(parentIdentifier, options)
          .then((answer) => answer.body.children)
          .catch((): TocEntry[] => [])
      : Promise.resolve<TocEntry[]>([]),
  ]);
  model.summary = summary;
  model.citedBy = citedBy;
  model.parentChildren = parentChildren;

  if (isSection && xml) {
    const fragment = parseFragment(xml);
    const labels = await fetchLabels(citedIdentifiers(hrefs(fragment)), options);
    const target = unit.provision?.found ? unit.provision.identifier : null;
    model.sectionHtml = render(fragment, { target, labels });
  }

  if (isSection) {
    model.neighbors = sectionNeighbors(isPublicLaw ? (summary?.toc ?? []) : parentChildren, unit.served_identifier);
  }
  return model;
}
