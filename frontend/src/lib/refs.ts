/**
 * What a `<ref href="…">` in a rendered fragment becomes (the reader
 * contract, "Cross references"):
 *
 * | `href`                                                    | link                                   |
 * |-----------------------------------------------------------|----------------------------------------|
 * | `/us/usc/…`                                               | the US Code site; no hover text        |
 * | `/us/pl/`, `/us/pvtl/`, `/us/act/` with `exists: true`     | `/app{href}`; hover the law and unit   |
 * | `/us/stat/{v}/{p}` with `exists: true`                     | `/app/us/stat/{v}/{p}`; hover the first document's label |
 * | `/us/pl/{c}/{n}…` with `exists: false`, `c` ≥ 104          | govinfo's public-law link              |
 * | `/us/stat/{v}/{p}` with `exists: false`                    | govinfo's statute link                 |
 * | anything else, or no label for it                          | plain text                             |
 *
 * `fetchLabels` answers `{}` when the call failed, so every reference this
 * site would serve is then plain text.
 */

import type { Label, Labels } from "./types";
import { appHref, govinfoPlaw, govinfoStatute, parseStatPage, uscodeHref } from "./url";

const OWN = ["/us/pl/", "/us/pvtl/", "/us/act/", "/us/stat/"];
const PUBLIC_LAW = /^\/us\/pl\/(\d+)\/(\d+)/u;

/** govinfo's public-law link service starts at the 104th Congress. */
export const GOVINFO_PLAW_STARTS_AT = 104;

function stripQuery(href: string): string {
  return href.split(/[?#]/u)[0];
}

/** The identifiers a fragment's refs name that `/api/v1/labels` can answer:
 * this site's own prefixes, deduplicated, query and anchor stripped. */
export function citedIdentifiers(hrefs: string[]): string[] {
  const seen = new Set<string>();
  for (const href of hrefs) {
    if (!OWN.some((prefix) => href.startsWith(prefix))) continue;
    seen.add(stripQuery(href));
  }
  return [...seen];
}

export interface ResolvedRef {
  /** Where the link goes, or null for plain text. */
  href: string | null;
  /** Hover text, or null. */
  title: string | null;
}

const PLAIN: ResolvedRef = { href: null, title: null };

export function resolveRef(href: string, labels: Labels): ResolvedRef {
  const identifier = stripQuery(href);
  if (identifier.startsWith("/us/usc/")) {
    return { href: uscodeHref(identifier), title: null };
  }
  if (!OWN.some((prefix) => identifier.startsWith(prefix))) return PLAIN;

  const label: Label | undefined = labels[identifier];
  if (label === undefined) return PLAIN;

  if (label.exists) {
    if ("documents" in label) {
      return { href: appHref(identifier), title: label.documents[0]?.label ?? null };
    }
    const parts = [label.law_label];
    if (label.num) parts.push(`§ ${label.num}`);
    if (label.heading) parts.push(label.heading);
    return { href: appHref(identifier), title: parts.join(" ") };
  }

  const publicLaw = PUBLIC_LAW.exec(identifier);
  if (publicLaw && Number(publicLaw[1]) >= GOVINFO_PLAW_STARTS_AT) {
    return { href: govinfoPlaw(publicLaw[1], publicLaw[2]), title: null };
  }
  const page = parseStatPage(identifier);
  if (page) {
    return { href: govinfoStatute(page.volume, page.page), title: null };
  }
  return PLAIN;
}
