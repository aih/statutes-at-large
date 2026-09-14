import { describe, expect, it } from "vitest";

import { onlySection, sectionNeighbors, smallCapsClass } from "../src/lib/toc";
import type { TocEntry } from "../src/lib/types";

const s1: TocEntry = { identifier: "/us/pl/104/33/s1", level: "section", num: "1", heading: "Extension.", is_section: true };
const tI: TocEntry = { identifier: "/us/pl/1/1/tI", level: "title", num: "I", heading: null, is_section: false };
const tIs1: TocEntry = { ...s1, identifier: "/us/pl/1/1/tI/s1" };

describe("onlySection", () => {
  it("is the only child when that child is a section", () => {
    expect(onlySection([s1], null)).toBe(s1);
  });

  it("is the toc's section when the law summary counts one", () => {
    expect(onlySection([tI], { section_count: 1, toc: [tI, tIs1] })).toBe(tIs1);
  });

  it("is null for two sections or a node with no summary", () => {
    expect(onlySection([s1, tIs1], { section_count: 2, toc: [s1, tIs1] })).toBeNull();
    expect(onlySection([tI], null)).toBeNull();
  });
});

describe("smallCapsClass", () => {
  it("is smallCaps for a heading in lower case, as GPO types a small-caps heading", () => {
    expect(smallCapsClass("elimination of agricultural export subsidies")).toBe("smallCaps");
    expect(smallCapsClass("“elimination of agricultural export subsidies")).toBe("smallCaps");
    expect(smallCapsClass("authority of the secretary under section 32(c)")).toBe("smallCaps");
  });

  it("is undefined for a heading with any capital, no letters, or none at all", () => {
    expect(smallCapsClass("INTERNATIONAL MONETARY FUND")).toBeUndefined();
    expect(smallCapsClass("Short title")).toBeUndefined();
    expect(smallCapsClass("instructions to the United States executive director")).toBeUndefined();
    expect(smallCapsClass("[Reserved]")).toBeUndefined();
    expect(smallCapsClass("§ 12.")).toBeUndefined();
    expect(smallCapsClass("")).toBeUndefined();
    expect(smallCapsClass(null)).toBeUndefined();
  });
});

describe("sectionNeighbors", () => {
  const s804: TocEntry = {
    identifier: "/us/pl/98/181/tI/chI/tVIII/s804",
    level: "section",
    num: "804",
    heading: "instructions to the united states executive director",
    is_section: true,
  };
  const s805: TocEntry = { ...s804, identifier: "/us/pl/98/181/tI/chI/tVIII/s805", num: "805", heading: null };

  it("gives the label and the heading apart", () => {
    const { previous, next } = sectionNeighbors([tI, s804, s805], s805.identifier);
    expect(previous).toEqual({
      href: "/app/us/pl/98/181/tI/chI/tVIII/s804",
      label: "Sec. 804",
      heading: "instructions to the united states executive director",
    });
    expect(next).toBeNull();
  });
});
