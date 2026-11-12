import { describe, expect, it } from "vitest";

import {
  caseRedirect,
  editDistance,
  identifierIn,
  identifierSuggestions,
  lawNumberIn,
  similarity,
  suggestions,
} from "../src/lib/notfound";

describe("editDistance", () => {
  it("counts a swap of adjacent characters as one edit", () => {
    expect(editDistance("about", "abuot")).toBe(1);
    expect(editDistance("comps", "comp")).toBe(1);
    expect(editDistance("", "abc")).toBe(3);
    expect(similarity("x", "x")).toBe(1);
  });
});

describe("caseRedirect", () => {
  it("redirects a reader page asked for in another letter case", () => {
    expect(caseRedirect("/app/About")).toBe("/app/about");
    expect(caseRedirect("/app/SEARCH/Syntax/")).toBe("/app/search/syntax");
    expect(caseRedirect("/app/Congress")).toBe("/app/congress");
  });

  it("leaves a page in its own spelling and a path that is no page alone", () => {
    expect(caseRedirect("/app/about")).toBeNull();
    expect(caseRedirect("/app/about/")).toBeNull();
    expect(caseRedirect("/app/abuot")).toBeNull();
    expect(caseRedirect("/app/US/PL/81/740")).toBeNull();
  });
});

describe("identifierIn", () => {
  it("reads an identifier written without /us, in another case, or under /api/v1", () => {
    expect(identifierIn("/app/pl/81/740/s3")).toBe("/us/pl/81/740/s3");
    expect(identifierIn("/app/us/PL/81/740")).toBe("/us/pl/81/740");
    expect(identifierIn("/app/us/scomp/83/703/tI/ch1./s1")).toBe("/us/sComp/83/703/tI/ch1./s1");
    expect(identifierIn("/app/api/v1/us/stat/64/563")).toBe("/us/stat/64/563");
  });

  it("reads nothing out of a path that is not one", () => {
    expect(identifierIn("/app/about")).toBeNull();
    expect(identifierIn("/app/pl")).toBeNull();
  });
});

describe("lawNumberIn", () => {
  it("reads a law number from a segment", () => {
    expect(lawNumberIn("/app/81-740")).toEqual({ congress: 81, number: 740 });
    expect(lawNumberIn("/app/law/PL118-22")).toEqual({ congress: 118, number: 22 });
    expect(lawNumberIn("/app/Pub.L. 118-22")).toEqual({ congress: 118, number: 22 });
    expect(lawNumberIn("/app/2010-12-01")).toBeNull();
  });
});

describe("suggestions", () => {
  it("offers the reader pages spelled close to the path", () => {
    expect(suggestions("/app/abuot").map((l) => l.href)).toEqual(["/app/about"]);
    expect(suggestions("/app/congresses").map((l) => l.href)).toEqual(["/app/congress"]);
    expect(suggestions("/app/source").map((l) => l.href)).toEqual(["/app/sources"]);
  });

  it("puts an identifier or a law number first", () => {
    expect(suggestions("/app/pl/81/740")[0]).toEqual({ href: "/app/us/pl/81/740", label: "/us/pl/81/740" });
    expect(suggestions("/app/81-740")[0]).toEqual({ href: "/app/us/pl/81/740", label: "Public Law 81-740" });
  });

  it("offers nothing for a path close to no page", () => {
    expect(suggestions("/app/zzzzzzzz")).toEqual([]);
  });
});

describe("identifierSuggestions", () => {
  it("offers the law's Congress, or the index the identifier belongs to", () => {
    expect(identifierSuggestions("/us/pl/99/99999")).toEqual([
      { href: "/app/congress/99", label: "Laws of the 99th Congress" },
    ]);
    expect(identifierSuggestions("/us/pvtl/81/12/s1")[0].href).toBe("/app/congress/81");
    expect(identifierSuggestions("/us/sComp/1/1")[0].href).toBe("/app/comps");
    expect(identifierSuggestions("/us/act/1950-08-30/ch823")[0].href).toBe("/app/congress");
    expect(identifierSuggestions("/us/stat/999/1")).toEqual([]);
  });
});
