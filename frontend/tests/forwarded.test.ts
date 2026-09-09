/** The browser's address travels to the API as `X-Forwarded-For` on every
 * server-side call, and is absent when the page had none to give. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { callHeaders, fetchCite, fetchCitedBy, fetchLabels, fetchUnit } from "../src/lib/api";

function sentHeaders(): Record<string, string>[] {
  return vi.mocked(globalThis.fetch).mock.calls.map(([, init]) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    return Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  });
}

beforeEach(() => {
  globalThis.fetch = vi.fn(
    async () =>
      new Response(JSON.stringify({ exists: true, identifier: "/us/pl/81/740/s3" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  ) as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("callHeaders", () => {
  it("adds X-Forwarded-For when an address is given", () => {
    expect(callHeaders("application/json", { clientAddress: "203.0.113.5" })).toEqual({
      accept: "application/json",
      "x-forwarded-for": "203.0.113.5",
    });
  });

  it("sends no header for a null, missing or blank address", () => {
    expect(callHeaders("application/xml")).toEqual({ accept: "application/xml" });
    expect(callHeaders("application/xml", { clientAddress: null })).toEqual({ accept: "application/xml" });
    expect(callHeaders("application/xml", { clientAddress: "  " })).toEqual({ accept: "application/xml" });
  });
});

describe("the forwarded address", () => {
  it("goes with cite, the per-person route", async () => {
    await fetchCite("Pub. L. 81-740, § 3", { clientAddress: "203.0.113.5" });
    expect(sentHeaders()).toEqual([{ accept: "application/json", "x-forwarded-for": "203.0.113.5" }]);
  });

  it("goes with cited-by", async () => {
    await fetchCitedBy("/us/pl/81/740/s3", 20, { clientAddress: "198.51.100.7" });
    expect(sentHeaders()[0]["x-forwarded-for"]).toBe("198.51.100.7");
  });

  it("goes with every labels batch", async () => {
    const identifiers = Array.from({ length: 150 }, (_, i) => `/us/pl/118/${i + 1}`);
    await fetchLabels(identifiers, { clientAddress: "203.0.113.5" });
    const sent = sentHeaders();
    expect(sent).toHaveLength(2);
    for (const headers of sent) {
      expect(headers["x-forwarded-for"]).toBe("203.0.113.5");
      expect(headers["content-type"]).toBe("application/json");
    }
  });

  it("is absent when the page had none", async () => {
    await fetchUnit("/us/pl/81/740/s3");
    await fetchCite("64 Stat. 563");
    for (const headers of sentHeaders()) {
      expect(headers).not.toHaveProperty("x-forwarded-for");
    }
  });
});
