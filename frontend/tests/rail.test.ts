/**
 * `railNodes`: what the rail's "In this law" list shows. A hand-built tree
 * for the shapes (nesting, the open branch, a section-only law) and a slice
 * of `/api/v1/laws/117/328`'s `toc` (328 entries, over the 300 bound) cut
 * verbatim from the dev API for the bounded case against a real law.
 */
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { railNodes } from "../src/lib/rail";
import { nestToc, type TocLike } from "../src/lib/toc";

function entry(identifier: string, level: string, isSection = false): TocLike {
  return { identifier, level, num: null, heading: null, is_section: isSection };
}

function fixtureToc(): TocLike[] {
  const raw = JSON.parse(readFileSync(new URL("./fixtures/pl-117-328-toc-slice.json", import.meta.url), "utf8"));
  return raw as TocLike[];
}

describe("railNodes: the hand-built shapes", () => {
  const flat: TocLike[] = [
    entry("/us/pl/1/1/tI", "title"),
    entry("/us/pl/1/1/tI/s1", "section", true),
    entry("/us/pl/1/1/tI/s2", "section", true),
    entry("/us/pl/1/1/tII", "title"),
    entry("/us/pl/1/1/tII/s3", "section", true),
  ];
  const tree = nestToc(flat);

  it("lists every node, nested, when the total is at most the limit", () => {
    const nodes = railNodes(tree, "/us/pl/1/1/tI/s1");
    expect(nodes).toHaveLength(2);
    expect(nodes[0].entry.identifier).toBe("/us/pl/1/1/tI");
    expect(nodes[0].children).toHaveLength(2);
    expect(nodes[1].children).toHaveLength(1);
  });

  it("opens only the branch holding `current`", () => {
    const nodes = railNodes(tree, "/us/pl/1/1/tI/s1");
    expect(nodes[0].open).toBe(true);
    expect(nodes[1].open).toBe(false);
  });

  it("opens nothing when `current` is null", () => {
    const nodes = railNodes(tree, null);
    expect(nodes.every((node) => !node.open)).toBe(true);
    // Still nested in full below the limit: nothing is bounded away.
    expect(nodes[0].children).toHaveLength(2);
  });

  it("a leaf section carries no children; `open` is unused on a leaf", () => {
    const nodes = railNodes(tree, "/us/pl/1/1/tI/s1");
    const section = nodes[0].children[0];
    expect(section.entry.is_section).toBe(true);
    expect(section.children).toHaveLength(0);
  });

  it("a law with no hierarchy is a flat list of sections", () => {
    const sectionsOnly = nestToc([entry("/us/pl/1/2/s1", "section", true), entry("/us/pl/1/2/s2", "section", true)]);
    const nodes = railNodes(sectionsOnly, "/us/pl/1/2/s1");
    expect(nodes).toHaveLength(2);
    expect(nodes.every((node) => node.children.length === 0)).toBe(true);
  });
});

describe("railNodes: bounded above the limit, against a real law's toc", () => {
  const tree = nestToc(fixtureToc());
  const total = fixtureToc().length;

  it("the fixture is over the default limit", () => {
    expect(total).toBeGreaterThan(300);
  });

  it("keeps every hierarchy node at the top level", () => {
    const nodes = railNodes(tree, "/us/pl/117/328/dA/tVII/s701");
    const hierarchy = nodes.filter((node) => !node.entry.is_section);
    expect(hierarchy.map((node) => node.entry.identifier)).toEqual([
      "/us/pl/117/328/dA",
      "/us/pl/117/328/dB",
      "/us/pl/117/328/dC",
    ]);
  });

  it("opens only the branch holding `current`, and closes its siblings", () => {
    const nodes = railNodes(tree, "/us/pl/117/328/dA/tVII/s701");
    const [dA, dB, dC] = nodes.filter((node) => !node.entry.is_section);
    expect(dA.open).toBe(true);
    expect(dB.open).toBe(false);
    expect(dC.open).toBe(false);
  });

  it("a closed hierarchy node carries no children at all", () => {
    const nodes = railNodes(tree, "/us/pl/117/328/dA/tVII/s701");
    const [, dB, dC] = nodes.filter((node) => !node.entry.is_section);
    expect(dB.children).toHaveLength(0);
    expect(dC.children).toHaveLength(0);
  });

  it("the open branch's own sections are listed", () => {
    const nodes = railNodes(tree, "/us/pl/117/328/dA/tVII/s701");
    const [dA] = nodes.filter((node) => !node.entry.is_section);
    expect(dA.children.length).toBeGreaterThan(0);
  });
});
