/** `fetchLabels`: `POST /api/v1/labels` at 100 per request, merged, `{}` on failure. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LABELS_MAX, LABELS_PER_REQUEST, fetchLabels } from "../src/lib/api";

interface Call {
  url: string;
  method: string;
  identifiers: string[];
}

function calls(): Call[] {
  return vi.mocked(globalThis.fetch).mock.calls.map(([url, init]) => ({
    url: String(url),
    method: init?.method ?? "GET",
    identifiers: (JSON.parse(String(init?.body ?? "{}")) as { identifiers?: string[] }).identifiers ?? [],
  }));
}

function many(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `/us/pl/118/${i + 1}`);
}

beforeEach(() => {
  globalThis.fetch = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
    const asked = (JSON.parse(String(init?.body ?? "{}")) as { identifiers: string[] }).identifiers;
    const body = Object.fromEntries(asked.map((id) => [id, { exists: false }]));
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchLabels", () => {
  it("asks for nothing when there is nothing to ask about", async () => {
    expect(await fetchLabels([])).toEqual({});
    expect(calls()).toHaveLength(0);
  });

  it("posts JSON to /api/v1/labels", async () => {
    await fetchLabels(["/us/pl/81/740/s3"]);
    const [call] = calls();
    expect(call.url).toMatch(/\/api\/v1\/labels$/u);
    expect(call.method).toBe("POST");
    expect(call.identifiers).toEqual(["/us/pl/81/740/s3"]);
  });

  it("sends one request when the list fits", async () => {
    await fetchLabels(many(LABELS_PER_REQUEST));
    expect(calls()).toHaveLength(1);
    expect(calls()[0].identifiers).toHaveLength(LABELS_PER_REQUEST);
  });

  it("never puts more than 100 in one request, and asks about each once", async () => {
    const wanted = many(242);
    const labels = await fetchLabels(wanted);
    const sent = calls();
    expect(sent).toHaveLength(3);
    for (const call of sent) expect(call.identifiers.length).toBeLessThanOrEqual(LABELS_PER_REQUEST);
    expect(sent.flatMap((call) => call.identifiers)).toEqual(wanted);
    expect(Object.keys(labels)).toHaveLength(wanted.length);
  });

  it("stops at the bound", async () => {
    await fetchLabels(many(LABELS_MAX + 50));
    expect(calls()).toHaveLength(LABELS_MAX / LABELS_PER_REQUEST);
  });

  it("answers {} when a request fails", async () => {
    globalThis.fetch = vi.fn(async () => new Response("{\"detail\":\"boom\"}", { status: 500 })) as unknown as typeof fetch;
    expect(await fetchLabels(many(3))).toEqual({});
  });

  it("answers {} when fetch throws", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    expect(await fetchLabels(many(3))).toEqual({});
  });

  it("matches the bound the API enforces", () => {
    expect(LABELS_PER_REQUEST).toBe(100);
  });
});
