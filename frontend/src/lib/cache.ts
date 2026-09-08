/**
 * The reader's `Cache-Control` values (the reader contract, "Caching"): a unit
 * page copies the API's header; `/app/` and a stat page are `max-age=300`;
 * a failed `/app/goto` and every error page are `no-store`.
 */

export const IMMUTABLE = "public, max-age=31536000, immutable";
export const REVALIDATE = "public, max-age=300";
export const NO_STORE = "private, no-store";

/** The API's `Cache-Control` when it sent one, else `max-age=300`. */
export function copiedCacheControl(fromApi: string | null | undefined): string {
  return fromApi && fromApi.trim() !== "" ? fromApi : REVALIDATE;
}
