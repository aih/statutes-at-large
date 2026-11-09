/**
 * What the reader's 404 offers (`pages/404.astro`, and `ErrorPage` on a 404
 * from the API): the reader's pages, links whose spelling is close to the
 * path asked for, and a law or identifier read out of the path. A path that
 * differs from one of the reader's pages only in letter case is redirected
 * there (`caseRedirect`).
 */
import type { Link } from "./types";
import { APP, appHref, compsHref, congressHref, congressOrdinal, congressesHref, uscodeHref } from "./url";

/** The reader's pages that take no parameters, with the label the 404 lists them under. */
export const READER_PAGES: Link[] = [
  { href: `${APP}/`, label: "Home: look up a citation" },
  { href: congressesHref(), label: "Laws by Congress" },
  { href: compsHref(), label: "Statute Compilations" },
  { href: `${APP}/search`, label: "Search the text" },
  { href: `${APP}/search/syntax`, label: "Search syntax" },
  { href: `${APP}/sources`, label: "Sources" },
  { href: `${APP}/about`, label: "About this site" },
];

/** Every page the 404 lists: the reader's, the API docs, the US Code site. */
export const SITE_PAGES: Link[] = [
  ...READER_PAGES,
  { href: "/docs", label: "API documentation" },
  { href: uscodeHref("/"), label: "The US Code site" },
];

/** The similarity a page path must reach to be offered. */
export const CUTOFF = 0.75;

const KINDS: Record<string, string> = { pl: "pl", pvtl: "pvtl", act: "act", stat: "stat", scomp: "sComp" };

/** `/app/About/` → `/about`; `/app` → `/`. Lower case, no trailing slash. */
function normalise(path: string): string {
  const rest = path.startsWith(`${APP}/`) || path === APP ? path.slice(APP.length) : path;
  return rest.toLowerCase().replace(/\/+$/u, "") || "/";
}

function decoded(path: string): string {
  try {
    return decodeURIComponent(path);
  } catch {
    return path;
  }
}

/** Edit distance counting a swap of two adjacent characters as one edit. */
export function editDistance(a: string, b: string): number {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const d: number[][] = Array.from({ length: rows }, (_, i) => Array.from({ length: cols }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[a.length][b.length];
}

/** 1 for equal strings, 0 for strings with nothing in common. */
export function similarity(a: string, b: string): number {
  const longest = Math.max(a.length, b.length);
  return longest === 0 ? 1 : 1 - editDistance(a, b) / longest;
}

/** The reader page `path` names in another letter case, or null. */
export function caseRedirect(path: string): string | null {
  const wanted = normalise(path);
  const page = READER_PAGES.find((p) => normalise(p.href) === wanted);
  if (!page || page.href === path || `${page.href}/` === path) return null;
  return page.href;
}

/**
 * The identifier `path` means when it is one with the wrong case, without
 * `/us`, or under `/api/v1`: `/app/pl/81/740` and `/app/us/PL/81/740` are
 * `/us/pl/81/740`.
 */
export function identifierIn(path: string): string | null {
  const rest = decoded(path.startsWith(`${APP}/`) ? path.slice(APP.length) : path);
  const match = /^\/(?:api\/v1\/)?(?:us\/)?(pl|pvtl|act|stat|scomp)(\/[^?#]+)$/iu.exec(rest);
  if (!match) return null;
  const identifier = `/us/${KINDS[match[1].toLowerCase()]}${match[2].replace(/\/+$/u, "")}`;
  return identifier === rest ? null : identifier;
}

/** A segment of `path` that is a law number (`81-740`, `PL81-740`, `Pub.L.81-740`). */
export function lawNumberIn(path: string): { congress: number; number: number } | null {
  for (const segment of decoded(path).split("/")) {
    const match = /^(?:pub\.?\s*l\.?|p\.?\s*l\.?)?\s*(\d{1,3})[-–](\d{1,5})$/iu.exec(segment.trim());
    if (match) return { congress: Number(match[1]), number: Number(match[2]) };
  }
  return null;
}

/** Links for a path the reader has no route for, best first, at most five. */
export function suggestions(path: string): Link[] {
  const out: Link[] = [];
  const identifier = identifierIn(path);
  if (identifier) out.push({ href: appHref(identifier), label: identifier });
  const law = identifier ? null : lawNumberIn(path);
  if (law) out.push({ href: appHref(`/us/pl/${law.congress}/${law.number}`), label: `Public Law ${law.congress}-${law.number}` });

  const wanted = normalise(path);
  const close = READER_PAGES.map((page) => ({ page, score: similarity(wanted, normalise(page.href)) }))
    .filter(({ score }) => score >= CUTOFF && score < 1)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(({ page }) => page);
  out.push(...close);

  return out.filter((link, i) => out.findIndex((other) => other.href === link.href) === i).slice(0, 5);
}

/**
 * Links for an identifier the API answered 404 for: the law's Congress for a
 * public or private law, the compilations index for a compilation.
 */
export function identifierSuggestions(identifier: string): Link[] {
  const law = /^\/us\/(?:pl|pvtl)\/(\d+)\//u.exec(`${identifier}/`);
  if (law) {
    const congress = Number(law[1]);
    if (congress >= 1 && congress <= 200) {
      return [{ href: congressHref(congress), label: `Laws of the ${congressOrdinal(congress)} Congress` }];
    }
  }
  if (identifier.startsWith("/us/act/")) return [{ href: congressesHref(), label: "Laws by Congress" }];
  if (identifier.startsWith("/us/sComp/")) return [{ href: compsHref(), label: "Statute Compilations" }];
  return [];
}
