/**
 * The one place the reader calls `/api/v1`. Server-side `fetch` needs an
 * absolute URL, so every call goes through `BASE`: `API_BASE_URL` in compose
 * (`http://api:8001`), `http://localhost:8001` for `npm run dev`.
 *
 * Every call takes `CallOptions`. `clientAddress` is the browser's address
 * (`Astro.clientAddress`, which the Node adapter reads from the proxy's
 * `X-Forwarded-For`); it is sent as `X-Forwarded-For` so the API's per-address
 * limits on `cite` and `cited-by` key on the reader of the page and not on
 * this container. Without it every reader would share one bucket.
 */

import type {
  Cite,
  CitedBy,
  CompUnit,
  Labels,
  LawSummary,
  SearchResponse,
  StatPage,
  Status,
  Unit,
} from "./types";
import { API, apiHref, type Query } from "./url";

const BASE = process.env.API_BASE_URL ?? "http://localhost:8001";

/** Per-call settings: the browser's address to forward. */
export interface CallOptions {
  clientAddress?: string | null;
}

/** The request headers a call sends: `accept`, and the forwarded address when known. */
export function callHeaders(accept: string, options: CallOptions = {}): Record<string, string> {
  const headers: Record<string, string> = { accept };
  const address = options.clientAddress?.trim();
  if (address) headers["x-forwarded-for"] = address;
  return headers;
}

/** A non-2xx answer: the status, the `detail`, and the headers a page copies
 * (`Retry-After` on a 429). */
export class ApiError extends Error {
  status: number;
  detail: string;
  retryAfter: string | null;

  constructor(status: number, detail: string, retryAfter: string | null = null) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

/** A body with the response headers the page needs beside it. */
export interface Answer<T> {
  body: T;
  cacheControl: string | null;
}

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail != null) return JSON.stringify(detail);
  }
  return fallback;
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      detailOf(body, response.statusText || `HTTP ${response.status}`),
      response.headers.get("retry-after"),
    );
  }
  return response;
}

async function getJson<T>(path: string, options: CallOptions = {}): Promise<Answer<T>> {
  const response = await request(path, { headers: callHeaders("application/json", options) });
  return { body: (await response.json()) as T, cacheControl: response.headers.get("cache-control") };
}

async function getXml(path: string, options: CallOptions = {}): Promise<string> {
  const response = await request(path, { headers: callHeaders("application/xml", options) });
  return response.text();
}

/** An enacted unit: `GET /api/v1{identifier}`. */
export async function fetchUnit(identifier: string, options: CallOptions = {}): Promise<Answer<Unit>> {
  return getJson<Unit>(apiHref(identifier), options);
}

/** The stamped USLM of an enacted unit: `GET /api/v1{identifier}?format=xml`. */
export async function fetchUnitXml(identifier: string, options: CallOptions = {}): Promise<string> {
  return getXml(apiHref(identifier, { format: "xml" }), options);
}

/** A compiled unit: `GET /api/v1/us/sComp/…[?through=]`. */
export async function fetchCompUnit(
  identifier: string,
  through?: string | null,
  options: CallOptions = {},
): Promise<Answer<CompUnit>> {
  return getJson<CompUnit>(apiHref(identifier, { through }), options);
}

/** The USLM of a compiled unit, pinned to the same version. */
export async function fetchCompUnitXml(
  identifier: string,
  through?: string | null,
  options: CallOptions = {},
): Promise<string> {
  const query: Query = { format: "xml", through };
  return getXml(apiHref(identifier, query), options);
}

/** `GET /api/v1/laws/{c}/{n}`. */
export async function fetchLawSummary(congress: number, number: number, options: CallOptions = {}): Promise<LawSummary> {
  return (await getJson<LawSummary>(`${API}/laws/${congress}/${number}`, options)).body;
}

/** `GET /api/v1/us/stat/{volume}/{page}`. */
export async function fetchStatPage(volume: string, page: string, options: CallOptions = {}): Promise<Answer<StatPage>> {
  return getJson<StatPage>(apiHref(`/us/stat/${volume}/${page}`), options);
}

/** `GET /api/v1/status`; null when the call failed. */
export async function fetchStatus(options: CallOptions = {}): Promise<Status | null> {
  try {
    return (await getJson<Status>(`${API}/status`, options)).body;
  } catch {
    return null;
  }
}

/** `GET /api/v1/cite?q=`. A 422 arrives as `ApiError`. Limited per address by the API. */
export async function fetchCite(query: string, options: CallOptions = {}): Promise<Cite> {
  return (await getJson<Cite>(`${API}/cite?q=${encodeURIComponent(query)}`, options)).body;
}

/** Per-call settings for `fetchSearch`, beside the forwarded address. */
export interface SearchOptions extends CallOptions {
  limit?: number;
  offset?: number;
  sort?: string;
  /** `enacted`, `compiled` or `all`. Left off to take the API's default. */
  view?: string | null;
}

/**
 * `GET /api/v1/search?q=`. A 400 (nothing to search for, or a bad `sort`)
 * and a 503 (the cluster is unavailable) both arrive as `ApiError`.
 */
export async function fetchSearch(query: string, options: SearchOptions = {}): Promise<Answer<SearchResponse>> {
  const params = new URLSearchParams({ q: query });
  if (options.limit) params.set("limit", String(options.limit));
  if (options.offset) params.set("offset", String(options.offset));
  if (options.sort) params.set("sort", options.sort);
  if (options.view) params.set("view", options.view);
  return getJson<SearchResponse>(`${API}/search?${params.toString()}`, options);
}

/** `GET /api/v1/cited-by?identifier=&limit=`; null on a 404 or any failure.
 * Limited per address by the API. */
export async function fetchCitedBy(identifier: string, limit = 20, options: CallOptions = {}): Promise<CitedBy | null> {
  try {
    const params = new URLSearchParams({ identifier, limit: String(limit) });
    return (await getJson<CitedBy>(`${API}/cited-by?${params.toString()}`, options)).body;
  } catch {
    return null;
  }
}

/** The API's bound on one `POST /labels` body (`LabelsIn`, `max_length=100`). */
export const LABELS_PER_REQUEST = 100;

/** How many identifiers one page labels at most: ten requests' worth. */
export const LABELS_MAX = LABELS_PER_REQUEST * 10;

/**
 * `POST /api/v1/labels`, at most 100 identifiers per request, the answers
 * merged. `{}` when any request fails: the page then renders its references
 * as plain text.
 */
export async function fetchLabels(identifiers: string[], options: CallOptions = {}): Promise<Labels> {
  if (identifiers.length === 0) return {};
  const wanted = identifiers.slice(0, LABELS_MAX);
  const batches: string[][] = [];
  for (let i = 0; i < wanted.length; i += LABELS_PER_REQUEST) {
    batches.push(wanted.slice(i, i + LABELS_PER_REQUEST));
  }
  try {
    const answers = await Promise.all(
      batches.map(async (batch) => {
        const response = await request(`${API}/labels`, {
          method: "POST",
          headers: { ...callHeaders("application/json", options), "content-type": "application/json" },
          body: JSON.stringify({ identifiers: batch }),
        });
        return (await response.json()) as Labels;
      }),
    );
    return Object.assign({}, ...answers) as Labels;
  } catch {
    return {};
  }
}
