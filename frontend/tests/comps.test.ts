import { describe, expect, it } from "vitest";

import { compLetter, compMatches, compName, groupComps } from "../src/lib/comps";
import type { CompTitle } from "../src/lib/types";

function comp(file_id: string, display_title: string | null, extra: Partial<CompTitle> = {}): CompTitle {
  return {
    file_id,
    package_id: `COMPS-${file_id}`,
    identifier_prefix: `/us/sComp/1/${file_id}`,
    identifier: `/us/sComp/1/${file_id}`,
    display_title,
    title: null,
    partial_of: null,
    current_through: null,
    ...extra,
  };
}

describe("the compilations index", () => {
  it("names a file by display title, official title, then prefix", () => {
    expect(compName(comp("1", "Atomic Energy Act of 1954"))).toBe("Atomic Energy Act of 1954");
    expect(compName(comp("2", null, { title: "To amend" }))).toBe("To amend");
    expect(compName(comp("3", null))).toBe("/us/sComp/1/3");
  });

  it("files a name under its first letter, ignoring leading punctuation", () => {
    expect(compLetter(comp("1", "atomic"))).toBe("A");
    expect(compLetter(comp("2", "“Ébola” Act"))).toBe("E");
    expect(compLetter(comp("3", "1921 Silver Dollar Coin Anniversary Act"))).toBe("#");
  });

  it("groups # first, then A to Z, sorted by name with numbers as numbers", () => {
    const groups = groupComps([
      comp("1", "Zoo Act"),
      comp("2", "Act of 1990"),
      comp("3", "1921 Silver Dollar"),
      comp("4", "Act of 202"),
      comp("5", "act of 1990"),
    ]);
    expect(groups.map((g) => g.letter)).toEqual(["#", "A", "Z"]);
    expect(groups[1].comps.map((c) => c.file_id)).toEqual(["4", "2", "5"]);
  });

  it("matches every word against the titles, the prefix and the package", () => {
    const c = comp("1630", "Atomic Energy Act of 1954", { title: "To amend the Atomic Energy Act of 1946" });
    expect(compMatches(c, "")).toBe(true);
    expect(compMatches(c, "energy 1946")).toBe(true);
    expect(compMatches(c, "COMPS-1630")).toBe(true);
    expect(compMatches(c, "/us/scomp/1/1630")).toBe(true);
    expect(compMatches(c, "energy tax")).toBe(false);
  });
});
