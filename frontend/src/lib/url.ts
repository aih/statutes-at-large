/**
 * Every href the reader builds. `APP` is the reader's prefix, `API` the
 * machine surface; the US Code site and govinfo are the two external hosts.
 */

export const APP = "/app";
export const API = "/api/v1";

/** The US Code site's origin, from `USCODE_ORIGIN` in the environment. */
export const USCODE_ORIGIN = (process.env.USCODE_ORIGIN ?? "https://uscode.linkedlegislation.org").replace(
  /\/+$/u,
  "",
);

export type Query = Record<string, string | number | null | undefined>;

function queryString(query: Query | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value == null || value === "") continue;
    params.set(key, String(value));
  }
  const built = params.toString();
  return built ? `?${built}` : "";
}

/**
 * Percent-encodes every path segment of an identifier and leaves `/` as `/`.
 * Identifiers carry `ch1.` and letters; a US Code section number can carry an
 * en dash, which a `Location:` header cannot.
 */
export function encodePath(identifier: string): string {
  return identifier
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

/** `/app{identifier}`, with an optional query (`through=` for a compilation). */
export function appHref(identifier: string, query?: Query): string {
  return `${APP}${encodePath(identifier)}${queryString(query)}`;
}

/** `/api/v1{identifier}`, with an optional query (`format=xml`, `through=`). */
export function apiHref(identifier: string, query?: Query): string {
  return `${API}${encodePath(identifier)}${queryString(query)}`;
}

/** `USCODE_ORIGIN{identifier}`: a US Code identifier on the US Code site. */
export function uscodeHref(identifier: string): string {
  return `${USCODE_ORIGIN}${encodePath(identifier)}`;
}

/** govinfo's link service for a public law, the 104th Congress onward. */
export function govinfoPlaw(congress: number | string, number: number | string): string {
  return `https://www.govinfo.gov/link/plaw/${congress}/public/${number}`;
}

/** govinfo's link service for a Statutes at Large page. */
export function govinfoStatute(volume: number | string, page: number | string): string {
  return `https://www.govinfo.gov/link/statute/${volume}/${page}`;
}

/** `/app/goto?q=…`, the citation box's action. */
export function gotoHref(query?: string | null): string {
  return query ? `${APP}/goto?q=${encodeURIComponent(query)}` : `${APP}/goto`;
}

/** `/api/v1/cited-by?identifier=…&limit=…`, the panel's link to the rest. */
export function citedByApiHref(identifier: string, limit: number, offset = 0): string {
  return `${API}/cited-by${queryString({ identifier, limit, offset: offset || null })}`;
}

const STAT_PAGE = /^\/us\/stat\/(\d+)\/([^/?#]+)/u;

/** `/us/stat/64/564` → `{ volume: "64", page: "564" }`, or null. */
export function parseStatPage(identifier: string): { volume: string; page: string } | null {
  const match = STAT_PAGE.exec(identifier);
  return match ? { volume: match[1], page: match[2] } : null;
}

/** A congress and law number from `/us/pl/118/22/…` or `/us/pvtl/…`, or null. */
export function parseLawNumber(identifier: string): { kind: string; congress: number; number: number } | null {
  const match = /^\/us\/(pl|pvtl)\/(\d+)\/(\d+)/u.exec(identifier);
  return match ? { kind: match[1], congress: Number(match[2]), number: Number(match[3]) } : null;
}

/** `1950-08-30` → `August 30, 1950`; anything else is returned as it is. */
export function longDate(value: string | null | undefined): string {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/u.exec(value);
  if (!match) return value;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return date.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}
