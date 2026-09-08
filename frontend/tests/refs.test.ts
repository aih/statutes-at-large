/** Every row of the contract's table for `resolveRef`, and `citedIdentifiers`. */
import { describe, expect, it } from "vitest";

import { citedIdentifiers, resolveRef } from "../src/lib/refs";
import type { Labels } from "../src/lib/types";

const labels: Labels = {
  "/us/pl/81/740/s3": {
    exists: true,
    served_identifier: "/us/pl/81/740/s3",
    resolution: "exact",
    num: "3",
    heading: null,
    level: "section",
    kind: "pl",
    law_identifier: "/us/pl/81/740",
    law_label: "Public Law 81-740",
    currency: { kind: "as_enacted", date: "1950-08-30", amended: { status: "no_record", latest: null, evidence: [] } },
  },
  "/us/pl/118/22/s101": {
    exists: true,
    served_identifier: "/us/pl/118/22/dA/s101",
    resolution: "section_number",
    num: "101",
    heading: "SHORT TITLE.",
    level: "section",
    kind: "pl",
    law_identifier: "/us/pl/118/22",
    law_label: "Public Law 118-22",
    currency: { kind: "as_enacted", date: "2023-11-17", amended: { status: "no_record", latest: null, evidence: [] } },
  },
  "/us/act/1950-08-30/ch823": {
    exists: true,
    served_identifier: "/us/pl/81/740",
    resolution: "alias",
    num: null,
    heading: "To incorporate the Future Farmers of America, and for other purposes.",
    level: "law",
    kind: "pl",
    law_identifier: "/us/pl/81/740",
    law_label: "Public Law 81-740",
    currency: { kind: "as_enacted", date: "1950-08-30", amended: { status: "no_record", latest: null, evidence: [] } },
  },
  "/us/stat/64/564": {
    exists: true,
    served_identifier: "/us/stat/64/564",
    resolution: "exact",
    num: "564",
    heading: null,
    level: "page",
    kind: "stat",
    volume: 64,
    page: "564",
    documents: [{ identifier: "/us/pl/81/740", label: "Public Law 81-740", kind: "pl", starts_here: false }],
    pdf: "https://www.govinfo.gov/link/statute/64/564",
  },
  "/us/pl/104/333/s814": { exists: false },
  "/us/pl/103/1": { exists: false },
  "/us/pvtl/99/1": { exists: false },
  "/us/act/1916-08-25/ch408": { exists: false },
  "/us/stat/110/4196": { exists: false },
};

describe("citedIdentifiers", () => {
  it("keeps this site's prefixes, deduplicated, query and anchor stripped", () => {
    expect(
      citedIdentifiers([
        "/us/pl/81/740/s3",
        "/us/pl/81/740/s3?view=compiled",
        "/us/pl/81/740/s3#x",
        "/us/pvtl/81/375",
        "/us/act/1950-08-30/ch823",
        "/us/stat/64/564",
        "/us/usc/t20/s151",
        "https://example.org/",
        "",
      ]),
    ).toEqual(["/us/pl/81/740/s3", "/us/pvtl/81/375", "/us/act/1950-08-30/ch823", "/us/stat/64/564"]);
  });

  it("is empty for a fragment with only US Code references", () => {
    expect(citedIdentifiers(["/us/usc/t20/s151"])).toEqual([]);
  });
});

describe("resolveRef", () => {
  it("/us/usc/… goes to the US Code site with no hover text", () => {
    expect(resolveRef("/us/usc/t43/s1701", labels)).toEqual({
      href: "https://uscode.linkedlegislation.org/us/usc/t43/s1701",
      title: null,
    });
  });

  it("/us/usc/… with an en dash is percent-encoded", () => {
    expect(resolveRef("/us/usc/t16/s3839bb–2", {}).href).toBe(
      "https://uscode.linkedlegislation.org/us/usc/t16/s3839bb%E2%80%932",
    );
  });

  it("a public law unit that exists goes to this site, hover law_label, num and heading", () => {
    expect(resolveRef("/us/pl/81/740/s3", labels)).toEqual({
      href: "/app/us/pl/81/740/s3",
      title: "Public Law 81-740 § 3",
    });
    expect(resolveRef("/us/pl/118/22/s101", labels).title).toBe("Public Law 118-22 § 101 SHORT TITLE.");
  });

  it("an act that exists goes to this site; the hover carries the law and heading", () => {
    expect(resolveRef("/us/act/1950-08-30/ch823", labels)).toEqual({
      href: "/app/us/act/1950-08-30/ch823",
      title: "Public Law 81-740 To incorporate the Future Farmers of America, and for other purposes.",
    });
  });

  it("a query or anchor on the href is dropped before the lookup", () => {
    expect(resolveRef("/us/pl/81/740/s3?view=compiled#a", labels).href).toBe("/app/us/pl/81/740/s3");
  });

  it("a Stat. page that exists goes to this site, hover the first document's label", () => {
    expect(resolveRef("/us/stat/64/564", labels)).toEqual({
      href: "/app/us/stat/64/564",
      title: "Public Law 81-740",
    });
  });

  it("a public law of the 104th Congress onward that does not exist goes to govinfo", () => {
    expect(resolveRef("/us/pl/104/333/s814", labels)).toEqual({
      href: "https://www.govinfo.gov/link/plaw/104/public/333",
      title: null,
    });
  });

  it("a public law before the 104th Congress that does not exist is plain text", () => {
    expect(resolveRef("/us/pl/103/1", labels)).toEqual({ href: null, title: null });
  });

  it("a Stat. page that does not exist goes to govinfo", () => {
    expect(resolveRef("/us/stat/110/4196", labels)).toEqual({
      href: "https://www.govinfo.gov/link/statute/110/4196",
      title: null,
    });
  });

  it("a private law or an act that does not exist is plain text", () => {
    expect(resolveRef("/us/pvtl/99/1", labels).href).toBeNull();
    expect(resolveRef("/us/act/1916-08-25/ch408", labels).href).toBeNull();
  });

  it("anything the labels call did not answer is plain text, even a 104th-Congress law", () => {
    expect(resolveRef("/us/pl/118/22", {}).href).toBeNull();
    expect(resolveRef("/us/stat/64/564", {}).href).toBeNull();
  });

  it("anything outside the five prefixes is plain text", () => {
    expect(resolveRef("https://www.govinfo.gov/", labels).href).toBeNull();
    expect(resolveRef("/us/cfr/t40/s1", labels).href).toBeNull();
    expect(resolveRef("", labels).href).toBeNull();
  });
});
