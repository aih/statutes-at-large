/**
 * The reader's `Cache-Control` values (the reader contract, "Caching"): every
 * page that answers 200 is `max-age=300`; a failed `/app/goto`, a failed
 * search and every error page are `no-store`. The API's own header is not
 * copied onto a page (ADR-0028).
 */

export const REVALIDATE = "public, max-age=300";
export const NO_STORE = "private, no-store";
