/**
 * The one place the reader calls `/api/v1`. Server-side `fetch` needs an
 * absolute URL, so every call goes through `BASE`: `API_BASE_URL` in compose
 * (`http://api:8001`), `http://localhost:8001` for `npm run dev`.
 */

import type {
  Cite,
  CitedBy,
  CompUnit,
  Labels,
  LawSummary,
  StatPage,
  Status,
  Unit,
} from "./types";
import { API, apiHref, type Query } from "./url";

const BASE = process.env.API_BASE_URL ?? "http://localhost:8001";

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

async function getJson<T>(path: string): Promise<Answer<T>> {
  const response = await request(path, { headers: { accept: "application/json" } });
  return { body: (await response.json()) as T, cacheControl: response.headers.get("cache-control") };
}

async function getXml(path: string): Promise<string> {
  const response = await request(path, { headers: { accept: "application/xml" } });
  return response.text();
}

/** An enacted unit: `GET /api/v1{identifier}`. */
export async function fetchUnit(identifier: string): Promise<Answer<Unit>> {
  return getJson<Unit>(apiHref(identifier));
}

/** The stamped USLM of an enacted unit: `GET /api/v1{identifier}?format=xml`. */
export async function fetchUnitXml(identifier: string): Promise<string> {
  return getXml(apiHref(identifier, { format: "xml" }));
}

/** A compiled unit: `GET /api/v1/us/sComp/…[?through=]`. */
export async function fetchCompUnit(identifier: string, through?: string | null): Promise<Answer<CompUnit>> {
  return getJson<CompUnit>(apiHref(identifier, { through }));
}

/** The USLM of a compiled unit, pinned to the same version. */
export async function fetchCompUnitXml(identifier: string, through?: string | null): Promise<string> {
  const query: Query = { format: "xml", through };
  return getXml(apiHref(identifier, query));
}

/** `GET /api/v1/laws/{c}/{n}`. */
export async function fetchLawSummary(congress: number, number: number): Promise<LawSummary> {
  return (await getJson<LawSummary>(`${API}/laws/${congress}/${number}`)).body;
}

/** `GET /api/v1/us/stat/{volume}/{page}`. */
export async function fetchStatPage(volume: string, page: string): Promise<Answer<StatPage>> {
  return getJson<StatPage>(apiHref(`/us/stat/${volume}/${page}`));
}

/** `GET /api/v1/status`; null when the call failed. */
export async function fetchStatus(): Promise<Status | null> {
  try {
    return (await getJson<Status>(`${API}/status`)).body;
  } catch {
    return null;
  }
}

/** `GET /api/v1/cite?q=`. A 422 arrives as `ApiError`. */
export async function fetchCite(query: string): Promise<Cite> {
  return (await getJson<Cite>(`${API}/cite?q=${encodeURIComponent(query)}`)).body;
}

/** `GET /api/v1/cited-by?identifier=&limit=`; null on a 404 or any failure. */
export async function fetchCitedBy(identifier: string, limit = 20): Promise<CitedBy | null> {
  try {
    const params = new URLSearchParams({ identifier, limit: String(limit) });
    return (await getJson<CitedBy>(`${API}/cited-by?${params.toString()}`)).body;
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
export async function fetchLabels(identifiers: string[]): Promise<Labels> {
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
          headers: { accept: "application/json", "content-type": "application/json" },
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
