import { describe, expect, it } from "vitest";

import { onlySection } from "../src/lib/toc";
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
