import { describe, expect, it } from "vitest";

import { nestToc, sectionNeighbors, unitLabel } from "../src/lib/toc";
import {
  apiHref,
  appHref,
  encodePath,
  gotoHref,
  govinfoPlaw,
  govinfoStatute,
  longDate,
  parseLawNumber,
  parseStatPage,
  uscodeHref,
} from "../src/lib/url";

describe("encodePath", () => {
  it("leaves plain identifiers alone, including a chapter with a period", () => {
    expect(encodePath("/us/sComp/83/703/tI/ch1./s1")).toBe("/us/sComp/83/703/tI/ch1./s1");
    expect(encodePath("/us/act/1950-08-30/ch823/s3")).toBe("/us/act/1950-08-30/ch823/s3");
  });

  it("percent-encodes every segment except the slashes", () => {
    expect(encodePath("/us/usc/t16/s45a–1")).toBe("/us/usc/t16/s45a%E2%80%931");
    expect(encodePath("/us/pl/1/1/s1 a?b#c")).toBe("/us/pl/1/1/s1%20a%3Fb%23c");
    expect(encodePath("/us/stat/64/A12")).toBe("/us/stat/64/A12");
  });
});

describe("hrefs", () => {
  it("appHref prefixes /app and carries a query", () => {
    expect(appHref("/us/pl/81/740/s3")).toBe("/app/us/pl/81/740/s3");
    expect(appHref("/us/sComp/83/703/tI/ch1./s1", { through: "118-67" })).toBe(
      "/app/us/sComp/83/703/tI/ch1./s1?through=118-67",
    );
    expect(appHref("/us/pl/81/740", { through: null })).toBe("/app/us/pl/81/740");
  });

  it("apiHref prefixes /api/v1", () => {
    expect(apiHref("/us/pl/81/740/s3", { format: "xml" })).toBe("/api/v1/us/pl/81/740/s3?format=xml");
  });

  it("uscodeHref is USCODE_ORIGIN plus the identifier", () => {
    expect(uscodeHref("/us/usc/t43/s1701")).toBe("https://uscode.linkedlegislation.org/us/usc/t43/s1701");
  });

  it("govinfo links", () => {
    expect(govinfoPlaw(118, 22)).toBe("https://www.govinfo.gov/link/plaw/118/public/22");
    expect(govinfoStatute("64", "564")).toBe("https://www.govinfo.gov/link/statute/64/564");
  });

  it("gotoHref encodes the query", () => {
    expect(gotoHref("Pub. L. 81-740, § 3")).toBe("/app/goto?q=Pub.%20L.%2081-740%2C%20%C2%A7%203");
    expect(gotoHref()).toBe("/app/goto");
  });
});

describe("parsers", () => {
  it("parseStatPage", () => {
    expect(parseStatPage("/us/stat/64/564")).toEqual({ volume: "64", page: "564" });
    expect(parseStatPage("/us/stat/64/a12")).toEqual({ volume: "64", page: "a12" });
    expect(parseStatPage("/us/pl/81/740")).toBeNull();
  });

  it("parseLawNumber", () => {
    expect(parseLawNumber("/us/pl/118/22/dA/s101")).toEqual({ kind: "pl", congress: 118, number: 22 });
    expect(parseLawNumber("/us/act/1950-08-30/ch823")).toBeNull();
  });

  it("longDate", () => {
    expect(longDate("1950-08-30")).toBe("August 30, 1950");
    expect(longDate(null)).toBe("");
    expect(longDate("2026-09-04T12:08:06Z")).toBe("2026-09-04T12:08:06Z");
  });
});

describe("tables of contents", () => {
  const toc = [
    { identifier: "/us/pl/118/22/s1", level: "section", num: "1", heading: "SHORT TITLE.", is_section: true },
    { identifier: "/us/pl/118/22/dA", level: "division", num: "A", heading: "A", is_section: false },
    { identifier: "/us/pl/118/22/dA/s101", level: "section", num: "101", heading: null, is_section: true },
    { identifier: "/us/pl/118/22/dB", level: "division", num: "B", heading: "B", is_section: false },
    { identifier: "/us/pl/118/22/dB/tI", level: "title", num: "I", heading: "T", is_section: false },
    { identifier: "/us/pl/118/22/dB/tI/s101", level: "section", num: "101", heading: "X", is_section: true },
  ];

  it("nests by identifier prefix", () => {
    const nodes = nestToc(toc);
    expect(nodes.map((node) => node.entry.identifier)).toEqual(["/us/pl/118/22/s1", "/us/pl/118/22/dA", "/us/pl/118/22/dB"]);
    expect(nodes[1].children.map((node) => node.entry.identifier)).toEqual(["/us/pl/118/22/dA/s101"]);
    expect(nodes[2].children[0].children.map((node) => node.entry.identifier)).toEqual(["/us/pl/118/22/dB/tI/s101"]);
  });

  it("finds the neighbouring sections across hierarchy", () => {
    expect(sectionNeighbors(toc, "/us/pl/118/22/dA/s101")).toEqual({
      previous: { href: "/app/us/pl/118/22/s1", label: "Sec. 1 SHORT TITLE." },
      next: { href: "/app/us/pl/118/22/dB/tI/s101", label: "Sec. 101 X" },
    });
    expect(sectionNeighbors(toc, "/us/pl/118/22/s1").previous).toBeNull();
    expect(sectionNeighbors(toc, "/us/pl/118/22/nope")).toEqual({ previous: null, next: null });
  });

  it("labels units", () => {
    expect(unitLabel("section", "101")).toBe("Sec. 101");
    expect(unitLabel("title", "I")).toBe("Title I");
    expect(unitLabel("chapter", "1.")).toBe("Chapter 1.");
    expect(unitLabel("law", null)).toBe("");
  });
});
